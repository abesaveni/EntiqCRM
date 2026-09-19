import React, { useState } from 'react';
import { Button } from './button';
import { Input } from './input';
import { Label } from './label';
import { Filter, X, Search, SlidersHorizontal, ArrowUpDown } from 'lucide-react';
import { cn } from './utils';

interface FilterOption {
  label: string;
  value: string;
}

interface FilterConfig {
  id: string;
  label: string;
  type: 'select' | 'multiselect' | 'range' | 'date' | 'search';
  options?: FilterOption[];
  placeholder?: string;
}

interface FiltersBarProps {
  filters: FilterConfig[];
  onFilterChange: (filterId: string, value: any) => void;
  onClearAll: () => void;
  activeFilters?: Record<string, any>;
  className?: string;
}

export function FiltersBar({ filters, onFilterChange, onClearAll, activeFilters = {}, className }: FiltersBarProps) {
  const [isExpanded, setIsExpanded] = useState(false);
  
  const activeFilterCount = Object.keys(activeFilters).filter(key => activeFilters[key]).length;

  return (
    <div className={cn('border rounded-lg bg-white', className)}>
      <div className="flex items-center justify-between p-4 border-b">
        <div className="flex items-center gap-2">
          <SlidersHorizontal className="w-5 h-5 text-gray-600" />
          <h3 className="font-semibold text-gray-900">Filters</h3>
          {activeFilterCount > 0 && (
            <span className="px-2 py-0.5 bg-primary text-white text-xs font-semibold rounded-full">
              {activeFilterCount}
            </span>
          )}
        </div>
        <div className="flex items-center gap-2">
          {activeFilterCount > 0 && (
            <Button variant="ghost" size="sm" onClick={onClearAll}>
              <X className="w-4 h-4 mr-1" />
              Clear All
            </Button>
          )}
          <Button
            variant="ghost"
            size="sm"
            onClick={() => setIsExpanded(!isExpanded)}
          >
            {isExpanded ? 'Hide' : 'Show'} Filters
          </Button>
        </div>
      </div>

      {isExpanded && (
        <div className="p-4 grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {filters.map((filter) => (
            <div key={filter.id}>
              <Label className="text-sm font-medium text-gray-700 mb-2 block">
                {filter.label}
              </Label>
              {filter.type === 'search' && (
                <div className="relative">
                  <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400" />
                  <Input
                    placeholder={filter.placeholder || 'Search...'}
                    value={activeFilters[filter.id] || ''}
                    onChange={(e) => onFilterChange(filter.id, e.target.value)}
                    className="pl-9"
                  />
                </div>
              )}
              {filter.type === 'select' && (
                <select
                  value={activeFilters[filter.id] || ''}
                  onChange={(e) => onFilterChange(filter.id, e.target.value)}
                  className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-primary"
                >
                  <option value="">All</option>
                  {filter.options?.map((option) => (
                    <option key={option.value} value={option.value}>
                      {option.label}
                    </option>
                  ))}
                </select>
              )}
              {filter.type === 'date' && (
                <Input
                  type="date"
                  value={activeFilters[filter.id] || ''}
                  onChange={(e) => onFilterChange(filter.id, e.target.value)}
                />
              )}
              {filter.type === 'range' && (
                <div className="flex gap-2">
                  <Input
                    type="number"
                    placeholder="Min"
                    value={activeFilters[filter.id]?.min || ''}
                    onChange={(e) => onFilterChange(filter.id, { ...activeFilters[filter.id], min: e.target.value })}
                  />
                  <Input
                    type="number"
                    placeholder="Max"
                    value={activeFilters[filter.id]?.max || ''}
                    onChange={(e) => onFilterChange(filter.id, { ...activeFilters[filter.id], max: e.target.value })}
                  />
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

interface SortOption {
  label: string;
  value: string;
}

interface SortBarProps {
  options: SortOption[];
  value: string;
  onChange: (value: string) => void;
  direction?: 'asc' | 'desc';
  onDirectionChange?: (direction: 'asc' | 'desc') => void;
  className?: string;
}

export function SortBar({ options, value, onChange, direction = 'asc', onDirectionChange, className }: SortBarProps) {
  return (
    <div className={cn('flex items-center gap-3', className)}>
      <span className="text-sm text-gray-600 font-medium">Sort by:</span>
      <select
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="px-3 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-primary text-sm"
      >
        {options.map((option) => (
          <option key={option.value} value={option.value}>
            {option.label}
          </option>
        ))}
      </select>
      {onDirectionChange && (
        <Button
          variant="outline"
          size="sm"
          onClick={() => onDirectionChange(direction === 'asc' ? 'desc' : 'asc')}
          className="flex items-center gap-2"
        >
          <ArrowUpDown className="w-4 h-4" />
          {direction === 'asc' ? 'Ascending' : 'Descending'}
        </Button>
      )}
    </div>
  );
}

// Search bar component
interface SearchBarProps {
  value: string;
  onChange: (value: string) => void;
  placeholder?: string;
  className?: string;
}

export function SearchBar({ value, onChange, placeholder = 'Search...', className }: SearchBarProps) {
  return (
    <div className={cn('relative', className)}>
      <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-5 h-5 text-gray-400" />
      <Input
        type="text"
        placeholder={placeholder}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="pl-10 pr-4"
      />
      {value && (
        <button
          onClick={() => onChange('')}
          className="absolute right-3 top-1/2 -translate-y-1/2 text-gray-400 hover:text-gray-600"
        >
          <X className="w-4 h-4" />
        </button>
      )}
    </div>
  );
}
