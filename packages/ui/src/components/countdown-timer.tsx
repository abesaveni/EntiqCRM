import React, { useState, useEffect } from 'react';
import { Clock } from 'lucide-react';
import { cn } from './utils';

interface CountdownTimerProps {
  endDate?: Date;
  end?: Date; // Support both prop names
  onExpire?: () => void;
  className?: string;
  variant?: 'default' | 'compact' | 'large';
}

export function CountdownTimer({ endDate, end, onExpire, className, variant = 'default' }: CountdownTimerProps) {
  const targetDate = endDate || end;
  
  // Return a placeholder if no date is provided
  if (!targetDate) {
    return <span className={className}>--:--:--</span>;
  }
  
  const [timeLeft, setTimeLeft] = useState(calculateTimeLeft(targetDate));

  useEffect(() => {
    if (!targetDate) return;
    
    const timer = setInterval(() => {
      const newTimeLeft = calculateTimeLeft(targetDate);
      setTimeLeft(newTimeLeft);

      if (newTimeLeft.total <= 0) {
        clearInterval(timer);
        onExpire?.();
      }
    }, 1000);

    return () => clearInterval(timer);
  }, [targetDate, onExpire]);

  if (timeLeft.total <= 0) {
    return (
      <div className={cn('text-red-600 font-semibold', className)}>
        Auction Ended
      </div>
    );
  }

  if (variant === 'compact') {
    return (
      <div className={cn('flex items-center gap-2 text-sm', className)}>
        <Clock className="w-4 h-4 text-gray-500" />
        <span>
          {timeLeft.days}d {timeLeft.hours}h {timeLeft.minutes}m
        </span>
      </div>
    );
  }

  if (variant === 'large') {
    return (
      <div className={cn('flex gap-4', className)}>
        <TimeUnit value={timeLeft.days} label="Days" />
        <TimeUnit value={timeLeft.hours} label="Hours" />
        <TimeUnit value={timeLeft.minutes} label="Minutes" />
        <TimeUnit value={timeLeft.seconds} label="Seconds" />
      </div>
    );
  }

  return (
    <div className={cn('flex items-center gap-2', className)}>
      <Clock className="w-5 h-5 text-gray-500" />
      <span className="font-semibold">
        {timeLeft.days > 0 && `${timeLeft.days}d `}
        {String(timeLeft.hours).padStart(2, '0')}:
        {String(timeLeft.minutes).padStart(2, '0')}:
        {String(timeLeft.seconds).padStart(2, '0')}
      </span>
    </div>
  );
}

function TimeUnit({ value, label }: { value: number; label: string }) {
  return (
    <div className="flex flex-col items-center">
      <div className="bg-gray-900 text-white rounded-lg px-4 py-2 min-w-[60px] text-center">
        <span className="text-2xl font-bold">{String(value).padStart(2, '0')}</span>
      </div>
      <span className="text-xs text-gray-600 mt-1">{label}</span>
    </div>
  );
}

function calculateTimeLeft(endDate: Date) {
  const total = endDate.getTime() - Date.now();
  
  if (total <= 0) {
    return { total: 0, days: 0, hours: 0, minutes: 0, seconds: 0 };
  }

  const seconds = Math.floor((total / 1000) % 60);
  const minutes = Math.floor((total / 1000 / 60) % 60);
  const hours = Math.floor((total / (1000 * 60 * 60)) % 24);
  const days = Math.floor(total / (1000 * 60 * 60 * 24));

  return { total, days, hours, minutes, seconds };
}