import React from 'react';
import { Home, ChevronRight } from 'lucide-react';

export interface BreadcrumbItem {
  label: string;
  onClick?: () => void;
  active?: boolean;
}

interface BreadcrumbsProps {
  items: BreadcrumbItem[];
  onHomeClick?: () => void;
  showHomeIcon?: boolean;
}

export function Breadcrumbs({ items, onHomeClick, showHomeIcon = true }: BreadcrumbsProps) {
  return (
    <nav className="flex items-center space-x-2 text-sm mb-6" aria-label="Breadcrumb">
      {showHomeIcon && (
        <>
          {onHomeClick ? (
            <button
              onClick={onHomeClick}
              className="text-gray-500 hover:text-gray-900 transition-colors focus:outline-none"
              type="button"
              aria-label="Home"
            >
              <Home className="w-4 h-4" />
            </button>
          ) : (
            <Home className="w-4 h-4 text-gray-500" />
          )}
        </>
      )}
      {items.map((item, index) => {
        const isFirst = index === 0;
        return (
          <div key={index} className="flex items-center space-x-2">
            {(!isFirst || showHomeIcon) && <ChevronRight className="w-4 h-4 text-gray-400" />}
            {item.active ? (
              <span className="font-medium text-gray-900" aria-current="page">
                {item.label}
              </span>
            ) : (
              <button
                onClick={item.onClick}
                className="text-gray-600 hover:text-gray-900 transition-colors focus:outline-none focus:underline"
                type="button"
              >
                {item.label}
              </button>
            )}
          </div>
        );
      })}
    </nav>
  );
}