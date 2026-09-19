import React, { useState } from 'react';
import { AlertTriangle, Info, CheckCircle, X } from 'lucide-react';
import { Button } from './button';

// Accepts BOTH prop conventions so every caller works:
//   * this component's native API:  isOpen / onClose
//   * the radix/shadcn-style API:   open / onOpenChange  (used by AdminUserManagement,
//     AdminKYCReview, CaseManagement, DocumentLibrary, EscrowRelease, ContractSigning, etc.)
// Before this, callers using open/onOpenChange rendered nothing (isOpen was undefined →
// `if (!isOpen) return null`), so their Suspend/Delete/confirm actions silently no-op'd.
type Variant = 'danger' | 'warning' | 'info' | 'success' | 'destructive' | 'default';

interface ConfirmDialogProps {
  isOpen?: boolean;
  open?: boolean;                              // alias for isOpen
  onClose?: () => void;
  onOpenChange?: (open: boolean) => void;      // alias for onClose
  onConfirm: () => void;
  title: string;
  description: string;
  confirmLabel?: string;
  cancelLabel?: string;
  variant?: Variant;
  isLoading?: boolean;
  children?: React.ReactNode;
}

export function ConfirmDialog({
  isOpen,
  open,
  onClose,
  onOpenChange,
  onConfirm,
  title,
  description,
  confirmLabel = 'Confirm',
  cancelLabel = 'Cancel',
  variant = 'warning',
  isLoading = false,
  children
}: ConfirmDialogProps) {
  const visible = isOpen ?? open ?? false;
  const close = () => { onClose?.(); onOpenChange?.(false); };
  // Normalize the radix-style variant values onto our config keys.
  const resolvedVariant: Exclude<Variant, 'destructive' | 'default'> =
    variant === 'destructive' ? 'danger' : variant === 'default' ? 'info' : variant;

  if (!visible) return null;

  const variantConfig = {
    danger: {
      icon: AlertTriangle,
      iconBg: 'bg-red-100',
      iconColor: 'text-red-600',
      buttonClass: 'bg-red-600 hover:bg-red-700'
    },
    warning: {
      icon: AlertTriangle,
      iconBg: 'bg-amber-100',
      iconColor: 'text-amber-600',
      buttonClass: 'bg-amber-600 hover:bg-amber-700'
    },
    info: {
      icon: Info,
      iconBg: 'bg-blue-100',
      iconColor: 'text-blue-600',
      buttonClass: 'bg-blue-600 hover:bg-blue-700'
    },
    success: {
      icon: CheckCircle,
      iconBg: 'bg-green-100',
      iconColor: 'text-green-600',
      buttonClass: 'bg-green-600 hover:bg-green-700'
    }
  };

  const config = variantConfig[resolvedVariant];
  const Icon = config.icon;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/50 backdrop-blur-sm">
      <div className="bg-white rounded-lg shadow-xl max-w-md w-full p-6 animate-in fade-in zoom-in duration-200">
        <div className="flex items-start gap-4">
          <div className={`flex-shrink-0 w-12 h-12 rounded-full flex items-center justify-center ${config.iconBg}`}>
            <Icon className={`w-6 h-6 ${config.iconColor}`} />
          </div>
          <div className="flex-1">
            <h3 className="text-lg font-semibold text-gray-900 mb-2">{title}</h3>
            <p className="text-sm text-gray-600 mb-6">{description}</p>
            {children}
            <div className="flex gap-3 justify-end mt-6">
              <Button
                variant="outline"
                onClick={close}
                disabled={isLoading}
              >
                {cancelLabel}
              </Button>
              <Button
                onClick={onConfirm}
                disabled={isLoading}
                className={config.buttonClass}
              >
                {isLoading ? 'Processing...' : confirmLabel}
              </Button>
            </div>
          </div>
          <button
            onClick={close}
            disabled={isLoading}
            className="flex-shrink-0 text-gray-400 hover:text-gray-600"
          >
            <X className="w-5 h-5" />
          </button>
        </div>
      </div>
    </div>
  );
}

// Hook for using confirm dialog
export function useConfirmDialog() {
  const [isOpen, setIsOpen] = useState(false);
  const [config, setConfig] = useState<{
    title: string;
    description: string;
    onConfirm: () => void;
    variant?: 'danger' | 'warning' | 'info' | 'success';
    confirmLabel?: string;
    cancelLabel?: string;
  } | null>(null);

  const confirm = (options: {
    title: string;
    description: string;
    onConfirm: () => void;
    variant?: 'danger' | 'warning' | 'info' | 'success';
    confirmLabel?: string;
    cancelLabel?: string;
  }) => {
    setConfig(options);
    setIsOpen(true);
    return new Promise<boolean>((resolve) => {
      const handleConfirm = () => {
        options.onConfirm();
        setIsOpen(false);
        resolve(true);
      };
      const handleCancel = () => {
        setIsOpen(false);
        resolve(false);
      };
    });
  };

  const Dialog = config ? (
    <ConfirmDialog
      isOpen={isOpen}
      onClose={() => setIsOpen(false)}
      onConfirm={() => {
        config.onConfirm();
        setIsOpen(false);
      }}
      title={config.title}
      description={config.description}
      variant={config.variant}
      confirmLabel={config.confirmLabel}
      cancelLabel={config.cancelLabel}
    />
  ) : null;

  return { confirm, Dialog };
}
