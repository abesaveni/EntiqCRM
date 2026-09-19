import React, { ReactNode } from 'react';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
} from './dialog';
import { Button } from './button';

interface ActionModalProps {
  title: string;
  isOpen: boolean;
  onClose: () => void;
  onConfirm: () => void;
  confirmLabel?: string;
  cancelLabel?: string;
  children: ReactNode;
}

export const ActionModal: React.FC<ActionModalProps> = ({
  title,
  isOpen,
  onClose,
  onConfirm,
  confirmLabel = 'Confirm',
  cancelLabel = 'Cancel',
  children,
}) => {
  return (
    <Dialog open={isOpen} onOpenChange={(open) => { if (!open) onClose(); }}>
      <DialogContent className="bg-white/95 backdrop-blur-md rounded-lg p-6 max-w-lg mx-auto">
        <DialogHeader>
          <DialogTitle>{title}</DialogTitle>
        </DialogHeader>
        <div className="space-y-4 py-4">{children}</div>
        <DialogFooter className="flex justify-end space-x-2 mt-4">
          <Button variant="outline" onClick={onClose}>
            {cancelLabel}
          </Button>
          <Button variant="default" onClick={onConfirm}>
            {confirmLabel}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
};
