"use client";

import * as DialogPrimitive from "@radix-ui/react-dialog";
import type { ComponentProps, ReactNode } from "react";

export function Dialog(props: ComponentProps<typeof DialogPrimitive.Root>) {
  return <DialogPrimitive.Root {...props} />;
}

export function DialogContent({
  className = "",
  children,
  ...props
}: ComponentProps<typeof DialogPrimitive.Content> & { children: ReactNode }) {
  return (
    <DialogPrimitive.Portal>
      <DialogPrimitive.Overlay className="fixed inset-0 z-[70] animate-fade bg-black/50" />
      <DialogPrimitive.Content
        className={`fixed top-1/2 left-1/2 z-[71] w-[min(448px,calc(100vw-32px))] -translate-x-1/2 -translate-y-1/2 animate-modal-in rounded-[24px] bg-canvas p-[24px] shadow-[0_16px_48px_rgba(0,0,0,0.18)] focus:outline-none ${className}`}
        {...props}
      >
        {children}
      </DialogPrimitive.Content>
    </DialogPrimitive.Portal>
  );
}

export function DialogTitle(props: ComponentProps<typeof DialogPrimitive.Title>) {
  return (
    <DialogPrimitive.Title
      className="m-0 mb-[8px] text-[1.125rem] font-semibold tracking-[-0.01em] text-ink"
      {...props}
    />
  );
}

export function DialogDescription(props: ComponentProps<typeof DialogPrimitive.Description>) {
  return (
    <DialogPrimitive.Description
      className="m-0 mb-[20px] text-[0.875rem] leading-[1.55] text-ink-soft"
      {...props}
    />
  );
}

export function DialogFooter({ children }: { children: ReactNode }) {
  return <div className="flex justify-end gap-[8px]">{children}</div>;
}

export function DialogClose(props: ComponentProps<typeof DialogPrimitive.Close>) {
  return <DialogPrimitive.Close {...props} />;
}
