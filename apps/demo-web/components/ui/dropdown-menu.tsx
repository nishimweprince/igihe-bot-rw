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
      <DropdownMenuPrimitive.Content className={`menu ${className}`} sideOffset={6} {...props} />
    </DropdownMenuPrimitive.Portal>
  );
}

export function DropdownMenuItem({
  className = "",
  ...props
}: ComponentProps<typeof DropdownMenuPrimitive.Item>) {
  return <DropdownMenuPrimitive.Item className={`menu-item ${className}`} {...props} />;
}
