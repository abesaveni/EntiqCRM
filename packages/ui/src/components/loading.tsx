import React from 'react';
import { Loader2 } from 'lucide-react';
import { cn } from './utils';

interface LoadingSpinnerProps {
  size?: 'sm' | 'md' | 'lg' | 'xl';
  text?: string;
  className?: string;
  fullScreen?: boolean;
}

export function LoadingSpinner({ size = 'md', text, className, fullScreen = false }: LoadingSpinnerProps) {
  const sizeClasses = {
    sm: 'w-4 h-4',
    md: 'w-8 h-8',
    lg: 'w-12 h-12',
    xl: 'w-16 h-16'
  };

  const spinner = (
    <div className={cn('flex flex-col items-center justify-center gap-3', className)}>
      <Loader2 className={cn('animate-spin text-primary', sizeClasses[size])} />
      {text && <p className="text-sm text-gray-600">{text}</p>}
    </div>
  );

  if (fullScreen) {
    return (
      <div className="fixed inset-0 bg-white/80 backdrop-blur-sm z-50 flex items-center justify-center">
        {spinner}
      </div>
    );
  }

  return spinner;
}

// Skeleton loader for cards and content
interface SkeletonProps {
  className?: string;
  variant?: 'text' | 'circular' | 'rectangular';
}

export function Skeleton({ className, variant = 'rectangular' }: SkeletonProps) {
  const variantClasses = {
    text: 'h-4 rounded',
    circular: 'rounded-full',
    rectangular: 'rounded-lg'
  };

  return (
    <div className={cn('animate-pulse bg-gray-200', variantClasses[variant], className)} />
  );
}

// Card skeleton for dashboard cards
export function CardSkeleton() {
  return (
    <div className="border rounded-lg p-6 space-y-4">
      <div className="flex items-center justify-between">
        <Skeleton className="w-12 h-12" variant="circular" />
        <Skeleton className="w-16 h-6" />
      </div>
      <Skeleton className="w-24 h-4" />
      <Skeleton className="w-32 h-8" />
      <Skeleton className="w-full h-3" />
    </div>
  );
}

// Table skeleton
export function TableSkeleton({ rows = 5, columns = 4 }: { rows?: number; columns?: number }) {
  return (
    <div className="space-y-3">
      {Array.from({ length: rows }).map((_, i) => (
        <div key={i} className="flex gap-4">
          {Array.from({ length: columns }).map((_, j) => (
            <Skeleton key={j} className="flex-1 h-10" />
          ))}
        </div>
      ))}
    </div>
  );
}
