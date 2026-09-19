import React, { useState } from 'react';
import { Search, SlidersHorizontal, X } from 'lucide-react';
import { Input } from './input';
import { Button } from './button';
import { Card, CardContent, CardHeader, CardTitle } from './card';
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from './popover';
import { Label } from './label';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from './select';

interface FilterOption {
  id: string;
  label: string;
  type: 'select' | 'range' | 'checkbox';
  options?: { value: string; label: string }[];
  min?: number;
  max?: number;
}

interface SearchFilterProps {
  placeholder?: string;
  onSearch: (query: string) => void;
  filters?: FilterOption[];
  onFilterChange?: (filters: Record<string, any>) => void;
}

export function SearchFilter({
  placeholder = 'Search...',
  onSearch,
  filters = [],
  onFilterChange
}: SearchFilterProps) {
  const [searchQuery, setSearchQuery] = useState('');
  const [filterValues, setFilterValues] = useState<Record<string, any>>({});
  const [isFilterOpen, setIsFilterOpen] = useState(false);

  const handleSearchChange = (value: string) => {
    setSearchQuery(value);
    onSearch(value);
  };

  const handleClearSearch = () => {
    setSearchQuery('');
    onSearch('');
  };

  const handleFilterChange = (filterId: string, value: any) => {
    const newFilters = { ...filterValues, [filterId]: value };
    setFilterValues(newFilters);
    onFilterChange?.(newFilters);
  };

  const handleClearFilters = () => {
    setFilterValues({});
    onFilterChange?.({});
  };

  const activeFilterCount = Object.values(filterValues).filter(v => v !== undefined && v !== '').length;

  return (
    <div className="flex gap-2">
      <div className="relative flex-1">
        <Search className="absolute left-3 top-1/2 transform -translate-y-1/2 w-4 h-4 text-gray-400" />
        <Input
          type="text"
          placeholder={placeholder}
          value={searchQuery}
          onChange={(e) => handleSearchChange(e.target.value)}
          className="pl-10 pr-10"
        />
        {searchQuery && (
          <button
            onClick={handleClearSearch}
            className="absolute right-3 top-1/2 transform -translate-y-1/2"
          >
            <X className="w-4 h-4 text-gray-400 hover:text-gray-600" />
          </button>
        )}
      </div>

      {filters.length > 0 && (
        <Popover open={isFilterOpen} onOpenChange={setIsFilterOpen}>
          <PopoverTrigger asChild>
            <Button variant="outline" className="relative">
              <SlidersHorizontal className="w-4 h-4 mr-2" />
              Filters
              {activeFilterCount > 0 && (
                <span className="absolute -top-2 -right-2 bg-indigo-600 text-white text-xs rounded-full w-5 h-5 flex items-center justify-center">
                  {activeFilterCount}
                </span>
              )}
            </Button>
          </PopoverTrigger>
          <PopoverContent className="w-80" align="end">
            <div className="space-y-4">
              <div className="flex items-center justify-between">
                <h4 className="font-semibold">Filters</h4>
                {activeFilterCount > 0 && (
                  <Button variant="ghost" size="sm" onClick={handleClearFilters}>
                    Clear all
                  </Button>
                )}
              </div>
              
              {filters.map((filter) => (
                <div key={filter.id} className="space-y-2">
                  <Label>{filter.label}</Label>
                  {filter.type === 'select' && filter.options && (
                    <Select
                      value={filterValues[filter.id] || ''}
                      onValueChange={(value) => handleFilterChange(filter.id, value)}
                    >
                      <SelectTrigger>
                        <SelectValue placeholder="Select..." />
                      </SelectTrigger>
                      <SelectContent>
                        {filter.options.map((option) => (
                          <SelectItem key={option.value} value={option.value}>
                            {option.label}
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  )}
                  {filter.type === 'range' && (
                    <div className="flex gap-2">
                      <Input
                        type="number"
                        placeholder="Min"
                        value={filterValues[`${filter.id}_min`] || ''}
                        onChange={(e) => handleFilterChange(`${filter.id}_min`, e.target.value)}
                      />
                      <Input
                        type="number"
                        placeholder="Max"
                        value={filterValues[`${filter.id}_max`] || ''}
                        onChange={(e) => handleFilterChange(`${filter.id}_max`, e.target.value)}
                      />
                    </div>
                  )}
                </div>
              ))}
            </div>
          </PopoverContent>
        </Popover>
      )}
    </div>
  );
}
