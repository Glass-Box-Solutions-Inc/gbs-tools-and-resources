import * as React from "react";
import { cva, type VariantProps } from "class-variance-authority";
import { cn } from "@/lib/utils";

const badgeVariants = cva(
  "inline-flex items-center rounded-full border px-2.5 py-0.5 text-xs font-semibold transition-colors",
  {
    variants: {
      variant: {
        default:
          "border-transparent bg-primary text-primary-foreground",
        secondary:
          "border-transparent bg-secondary text-secondary-foreground",
        destructive:
          "border-transparent bg-destructive text-destructive-foreground",
        outline: "text-foreground",
        litigated: "border-transparent bg-violet-100 text-violet-800",
        ct: "border-transparent bg-amber-100 text-amber-800",
        psych: "border-transparent bg-pink-100 text-pink-800",
        ptd: "border-transparent bg-red-100 text-red-800",
        denied: "border-transparent bg-orange-100 text-orange-800",
        death: "border-transparent bg-slate-200 text-slate-800",
        expedited: "border-transparent bg-blue-100 text-blue-800",
        flag: "border-transparent bg-indigo-100 text-indigo-800",
      },
    },
    defaultVariants: {
      variant: "default",
    },
  },
);

export interface BadgeProps
  extends React.HTMLAttributes<HTMLDivElement>,
    VariantProps<typeof badgeVariants> {}

function Badge({ className, variant, ...props }: BadgeProps) {
  return (
    <div className={cn(badgeVariants({ variant }), className)} {...props} />
  );
}

export { Badge, badgeVariants };
