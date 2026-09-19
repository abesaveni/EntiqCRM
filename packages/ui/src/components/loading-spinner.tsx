import React from 'react';
import { Loader2 } from 'lucide-react';
import { cn } from './utils';

interface LoadingSpinnerProps {
  size?: 'sm' | 'md' | 'lg';
  className?: string;
}

export function LoadingSpinner({ size = 'md', className }: LoadingSpinnerProps) {
  const sizeClasses = {
    sm: 'w-4 h-4',
    md: 'w-6 h-6',
    lg: 'w-8 h-8'
  };

  return (
    <Loader2 className={cn('animate-spin text-gray-500', sizeClasses[size], className)} />
  );
}

interface LoadingOverlayProps {
  message?: string;
}

export function LoadingOverlay({ message = 'Loading...' }: LoadingOverlayProps) {
  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
      <div className="bg-white rounded-lg p-6 flex flex-col items-center gap-4">
        <LoadingSpinner size="lg" />
        <p className="text-gray-900 font-medium">{message}</p>
      </div>
    </div>
  );
}

interface LoadingStateProps {
  message?: string;
  children?: React.ReactNode;
}

export function LoadingState({ message = 'Loading...', children }: LoadingStateProps) {
  return (
    <div className="flex flex-col items-center justify-center py-12 gap-4">
      <LoadingSpinner size="lg" />
      <p className="text-gray-600">{message}</p>
      {children}
    </div>
  );
}