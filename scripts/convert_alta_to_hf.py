"""Convert ALTA SFT checkpoint to HF-Llama layout so mlx-lm can convert it.

ALTA (yalilabs) uses custom key names and a config without `model_type`,
which makes `mlx_lm.convert` fail with `KeyError: 'model_type'`.
Architecturally it is a Llama-style decoder (GQA, RoPE, SwiGLU, RMSNorm),
so we rename tensors to `LlamaForCausalLM` layout and emit a Llama config.

Usage:
    .venv/bin/python scripts/convert_alta_to_hf.py \
        --src models/alta-sft-v1.0 --dst models/alta-sft-v1.0-hf
"""

from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path

from safetensors.numpy import load_file, save_file


def build_llama_config(alta_cfg: dict) -> dict:
    embed_dim = alta_cfg["embed_dim"]
    num_q_heads = alta_cfg["num_query_heads"]
    # K-proj output dim / head_dim gives KV heads; fall back to groups math.
    return {
        "architectures": ["LlamaForCausalLM"],
        "model_type": "llama",
        "hidden_size": embed_dim,
        "num_hidden_layers": alta_cfg["num_blocks"],
        "num_attention_heads": num_q_heads,
        "num_key_value_heads": alta_cfg["num_kv_groups"],
        "intermediate_size": 2048,  # from w_up/w_down shapes, not ffn_expansion
        "hidden_act": "silu",
        "max_position_embeddings": alta_cfg["context_length"],
        "rms_norm_eps": alta_cfg["norm_eps"],
        "rope_theta": alta_cfg["rope_theta"],
        "vocab_size": alta_cfg["vocab_size"],
        "tie_word_embeddings": False,
        "attention_bias": False,
        "mlp_bias": False,
        "bos_token_id": 2,
        "eos_token_id": 3,
        "pad_token_id": 0,
        "unk_token_id": 1,
    }


def rename_keys(state: dict) -> dict:
    out: dict = {}
    for k, v in state.items():
        if k == "embedding.weight":
            out["model.embed_tokens.weight"] = v
        elif k == "norm_final.weight":
            out["model.norm.weight"] = v
        elif k == "lm_head.weight":
            out["lm_head.weight"] = v
        elif k.startswith("blocks."):
            rest = k[len("blocks."):]  # "0.attn.q_proj.weight"
            idx, sub = rest.split(".", 1)
            mapping = {
                "attn.q_proj.weight": f"model.layers.{idx}.self_attn.q_proj.weight",
                "attn.k_proj.weight": f"model.layers.{idx}.self_attn.k_proj.weight",
                "attn.v_proj.weight": f"model.layers.{idx}.self_attn.v_proj.weight",
                "attn.out_proj.weight": f"model.layers.{idx}.self_attn.o_proj.weight",
                "attn_norm.weight": f"model.layers.{idx}.input_layernorm.weight",
                "ffn_norm.weight": f"model.layers.{idx}.post_attention_layernorm.weight",
                "ffn.ffn.w_up.weight": f"model.layers.{idx}.mlp.up_proj.weight",
                "ffn.ffn.w_gate.weight": f"model.layers.{idx}.mlp.gate_proj.weight",
                "ffn.ffn.w_down.weight": f"model.layers.{idx}.mlp.down_proj.weight",
            }
            if sub not in mapping:
                raise KeyError(f"unmapped ALTA key: {k}")
            out[mapping[sub]] = v
        else:
            raise KeyError(f"unmapped ALTA key: {k}")
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", required=True)
    ap.add_argument("--dst", required=True)
    args = ap.parse_args()

    src, dst = Path(args.src), Path(args.dst)
    alta_cfg = json.loads((src / "config.json").read_text())
    state = load_file(str(src / "model.safetensors"))

    # Derive KV heads from the actual K-proj shape as a sanity check.
    k_shape = state["blocks.0.attn.k_proj.weight"].shape  # (out, in)
    head_dim = alta_cfg["embed_dim"] // alta_cfg["num_query_heads"]
    kv_heads = k_shape[0] // head_dim
    if kv_heads != alta_cfg["num_kv_groups"]:
        raise SystemExit(
            f"KV-head mismatch: weight implies {kv_heads}, "
            f"config num_kv_groups={alta_cfg['num_kv_groups']}"
        )
    ffn_dim = state["blocks.0.ffn.ffn.w_up.weight"].shape[0]
    if ffn_dim != 2048:
        raise SystemExit(f"unexpected FFN dim {ffn_dim}, update intermediate_size")

    renamed = rename_keys(state)
    dst.mkdir(parents=True, exist_ok=True)
    save_file(renamed, str(dst / "model.safetensors"))
    (dst / "config.json").write_text(json.dumps(build_llama_config(alta_cfg), indent=2))
    for name in ("tokenizer.json", "tokenizer_config.json", "special_tokens_map.json"):
        p = src / name
        if p.exists():
            shutil.copy(p, dst / name)
    print(f"wrote {len(renamed)} tensors to {dst}")


if __name__ == "__main__":
    main()
