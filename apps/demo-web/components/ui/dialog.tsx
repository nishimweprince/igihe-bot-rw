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
      <DialogPrimitive.Overlay className="modal-overlay" />
      <DialogPrimitive.Content className={`modal ${className}`} {...props}>
        {children}
      </DialogPrimitive.Content>
    </DialogPrimitive.Portal>
  );
}

export function DialogTitle(props: ComponentProps<typeof DialogPrimitive.Title>) {
  return <DialogPrimitive.Title className="modal-title" {...props} />;
}

export function DialogDescription(props: ComponentProps<typeof DialogPrimitive.Description>) {
  return <DialogPrimitive.Description className="modal-body" {...props} />;
}

export function DialogFooter({ children }: { children: ReactNode }) {
  return <div className="modal-actions">{children}</div>;
}

export function DialogClose(props: ComponentProps<typeof DialogPrimitive.Close>) {
  return <DialogPrimitive.Close {...props} />;
}
