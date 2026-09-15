"use client";

import * as DropdownMenuPrimitive from "@radix-ui/react-dropdown-menu";
import type { ComponentProps } from "react";

export function DropdownMenu(props: ComponentProps<typeof DropdownMenuPrimitive.Root>) {
  return <DropdownMenuPrimitive.Root {...props} />;
}

export function DropdownMenuTrigger(props: ComponentProps<typeof DropdownMenuPrimitive.Trigger>) {
  return <DropdownMenuPrimitive.Trigger {...props} />;
}

export function DropdownMenuContent({
  className = "",
  ...props
}: ComponentProps<typeof DropdownMenuPrimitive.Content>) {
  return (
    <DropdownMenuPrimitive.Portal>
      <DropdownMenuPrimitive.Content
        className={`z-[60] min-w-[208px] origin-[var(--radix-dropdown-menu-content-transform-origin)] animate-pop-in rounded-[16px] border border-line bg-canvas p-[6px] shadow-[0_4px_24px_rgba(0,0,0,0.1)] ${className}`}
        sideOffset={6}
        {...props}
      />
    </DropdownMenuPrimitive.Portal>
  );
}

export function DropdownMenuItem({
  className = "",
  ...props
}: ComponentProps<typeof DropdownMenuPrimitive.Item>) {
  return (
    <DropdownMenuPrimitive.Item
      className={`flex min-h-[38px] w-full cursor-pointer items-center gap-[12px] rounded-[10px] border-0 bg-transparent px-[10px] py-[8px] text-[0.875rem] text-ink outline-none select-none data-[highlighted]:bg-hover [&_svg]:size-4 [&_svg]:shrink-0 [&_svg]:text-ink ${className}`}
      {...props}
    />
  );
}
