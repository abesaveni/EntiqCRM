"use client";

import * as React from "react";

import { cn } from "./utils";

function Table({ className, ...props }: React.ComponentProps<"table">) {
  return (
    <div
      data-slot="table-container"
      className="relative w-full overflow-x-auto"
    >
      <table
        data-slot="table"
        className={cn("w-full caption-bottom text-sm", className)}
        {...props}
      />
    </div>
  );
}

function TableHeader({ className, ...props }: React.ComponentProps<"thead">) {
  return (
    <thead
      data-slot="table-header"
      className={cn("[&_tr]:border-b", className)}
      {...props}
    />
  );
}

function TableBody({ className, ...props }: React.ComponentProps<"tbody">) {
  return (
    <tbody
      data-slot="table-body"
      className={cn("[&_tr:last-child]:border-0", className)}
      {...props}
    />
  );
}

function TableFooter({ className, ...props }: React.ComponentProps<"tfoot">) {
  return (
    <tfoot
      data-slot="table-footer"
      className={cn(
        "bg-muted/50 border-t font-medium [&>tr]:last:border-b-0",
        className,
      )}
      {...props}
    />
  );
}

function TableRow({ className, ...props }: React.ComponentProps<"tr">) {
  return (
    <tr
      data-slot="table-row"
      className={cn(
        "hover:bg-muted/50 data-[state=selected]:bg-muted border-b transition-colors",
        className,
      )}
      {...props}
    />
  );
}

function TableHead({ className, ...props }: React.ComponentProps<"th">) {
  return (
    <th
      data-slot="table-head"
      className={cn(
        "text-foreground h-10 px-2 text-left align-middle font-medium whitespace-nowrap [&:has([role=checkbox])]:pr-0 [&>[role=checkbox]]:translate-y-[2px]",
        className,
      )}
      {...props}
    />
  );
}

function TableCell({ className, ...props }: React.ComponentProps<"td">) {
  return (
    <td
      data-slot="table-cell"
      className={cn(
        "p-2 align-middle whitespace-nowrap [&:has([role=checkbox])]:pr-0 [&>[role=checkbox]]:translate-y-[2px]",
        className,
      )}
      {...props}
    />
  );
}

function TableCaption({
  className,
  ...props
}: React.ComponentProps<"caption">) {
  return (
    <caption
      data-slot="table-caption"
      className={cn("text-muted-foreground mt-4 text-sm", className)}
      {...props}
    />
  );
}


/**
 * A TableHead you can click to sort by.
 *
 * WHY THIS EXISTS ALONGSIDE SortableTh
 * ------------------------------------
 * `ent/useSortableRows` already ships a `SortableTh`, but it renders a bare
 * <th> styled with the Entiq design tokens. The admin and case screens use this
 * shadcn table, so dropping that in mixes two visual languages inside one header
 * row. This composes THEIR TableHead and adds only the affordance, so the column
 * still looks like every other column on the screen.
 *
 * It shares the exact SortState/toggle contract from useSortableRows — one
 * sorting engine, two presentations, rather than two implementations.
 */
function SortableTableHead({
  field,
  sort,
  toggle,
  children,
  className,
  align = 'left',
}: {
  field: string;
  sort: { key: string | null; dir: 'asc' | 'desc' };
  toggle: (key: string) => void;
  children: React.ReactNode;
  className?: string;
  align?: 'left' | 'right' | 'center';
}) {
  const active = sort.key === field;
  const alignCls =
    align === 'right' ? 'text-right' : align === 'center' ? 'text-center' : 'text-left';
  return (
    <TableHead
      role="button"
      tabIndex={0}
      // Announced to screen readers, not just drawn — a sort indicator nobody
      // can perceive is only half the feature.
      aria-sort={active ? (sort.dir === 'asc' ? 'ascending' : 'descending') : 'none'}
      onClick={() => toggle(field)}
      onKeyDown={(e) => {
        if (e.key === 'Enter' || e.key === ' ') {
          e.preventDefault();
          toggle(field);
        }
      }}
      className={cn(alignCls, 'cursor-pointer select-none hover:text-foreground', className)}
    >
      {children}
      <span
        aria-hidden
        className={cn('ml-1 inline-block text-[10px]', active ? 'opacity-100' : 'opacity-40')}
      >
        {active ? (sort.dir === 'asc' ? '▲' : '▼') : '↕'}
      </span>
    </TableHead>
  );
}

export {
  SortableTableHead,
  Table,
  TableHeader,
  TableBody,
  TableFooter,
  TableHead,
  TableRow,
  TableCell,
  TableCaption,
};
