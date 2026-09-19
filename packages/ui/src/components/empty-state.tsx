import React from 'react';
import { LucideIcon } from 'lucide-react';
import { Button } from './button';

interface EmptyStateAction {
  label: string;
  onClick: () => void;
}

interface EmptyStateProps {
  icon: LucideIcon;
  title: string;
  description: string;
  actionLabel?: string;
  onAction?: () => void;
  secondaryActionLabel?: string;
  onSecondaryAction?: () => void;
  /**
   * The action as one object, for callers that choose it conditionally —
   * `action={filtered ? clearFilters : uploadDocs}` reads far better than
   * juggling a matched pair of label/handler props through a ternary.
   *
   * Four screens were already passing this shape (Activity Feed, User
   * Management, Case Management, Document Library). The component did not
   * declare it, so React dropped it and the button silently never rendered —
   * their "Clear Filters" was decoration.
   */
  action?: EmptyStateAction;
}

export function EmptyState({
  icon: Icon,
  title,
  description,
  actionLabel,
  onAction,
  secondaryActionLabel,
  onSecondaryAction,
  action,
}: EmptyStateProps) {
  // Either spelling works. The paired props win if both are given, so nothing
  // that already worked changes behaviour.
  const primaryLabel = actionLabel ?? action?.label;
  const primaryOnClick = onAction ?? action?.onClick;
  return (
    <div className="flex flex-col items-center justify-center py-12 px-4 text-center">
      <div className="w-16 h-16 bg-gray-100 rounded-full flex items-center justify-center mb-4">
        <Icon className="w-8 h-8 text-gray-400" />
      </div>
      <h3 className="text-lg font-semibold text-gray-900 mb-2">{title}</h3>
      <p className="text-sm text-gray-600 max-w-md mb-6">{description}</p>
      {(primaryLabel || secondaryActionLabel) && (
        <div className="flex gap-3">
          {primaryLabel && primaryOnClick && (
            <Button onClick={primaryOnClick}>
              {primaryLabel}
            </Button>
          )}
          {secondaryActionLabel && onSecondaryAction && (
            <Button variant="outline" onClick={onSecondaryAction}>
              {secondaryActionLabel}
            </Button>
          )}
        </div>
      )}
    </div>
  );
}
