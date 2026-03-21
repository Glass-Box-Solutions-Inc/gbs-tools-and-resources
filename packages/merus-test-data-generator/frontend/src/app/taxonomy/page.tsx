"use client";

import { useEffect, useState } from "react";
import { Loader2, FileText, ChevronRight } from "lucide-react";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { getTypes, getSubtypes } from "@/lib/api/client";
import type { TaxonomyType, TaxonomySubtype } from "@/lib/api/types";
import { cn } from "@/lib/utils";

export default function TaxonomyPage() {
  const [types, setTypes] = useState<TaxonomyType[]>([]);
  const [subtypes, setSubtypes] = useState<TaxonomySubtype[]>([]);
  const [loading, setLoading] = useState(true);
  const [expandedType, setExpandedType] = useState<string | null>(null);

  useEffect(() => {
    async function fetchData() {
      try {
        const [typesData, subtypesData] = await Promise.all([
          getTypes(),
          getSubtypes(),
        ]);
        setTypes(typesData);
        setSubtypes(subtypesData);
      } catch {
        // ignore
      } finally {
        setLoading(false);
      }
    }
    fetchData();
  }, []);

  if (loading) {
    return (
      <div className="flex items-center justify-center py-24">
        <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
      </div>
    );
  }

  function getSubtypesForType(typeValue: string): TaxonomySubtype[] {
    return subtypes.filter((s) => s.parent_type === typeValue);
  }

  return (
    <div className="space-y-6">
      <Card>
        <CardHeader>
          <CardTitle>Document Taxonomy</CardTitle>
          <CardDescription>
            {types.length} parent types and {subtypes.length} subtypes available
            for test case generation.
          </CardDescription>
        </CardHeader>
      </Card>

      <div className="space-y-2">
        {types.map((type) => {
          const isExpanded = expandedType === type.value;
          const typeSubtypes = getSubtypesForType(type.value);

          return (
            <Card key={type.value}>
              <button
                onClick={() =>
                  setExpandedType(isExpanded ? null : type.value)
                }
                className="flex w-full items-center justify-between px-6 py-4 text-left hover:bg-muted/30"
              >
                <div className="flex items-center gap-3">
                  <FileText className="h-5 w-5 text-primary" />
                  <div>
                    <p className="text-sm font-medium text-foreground">
                      {type.label}
                    </p>
                    <p className="text-xs text-muted-foreground">
                      {type.value}
                    </p>
                  </div>
                </div>
                <div className="flex items-center gap-3">
                  <Badge variant="secondary">
                    {type.subtype_count} subtypes
                  </Badge>
                  <ChevronRight
                    className={cn(
                      "h-4 w-4 text-muted-foreground transition-transform",
                      isExpanded && "rotate-90",
                    )}
                  />
                </div>
              </button>

              {isExpanded && (
                <CardContent className="border-t pt-4">
                  <div className="grid grid-cols-2 gap-2">
                    {typeSubtypes.map((sub) => (
                      <div
                        key={sub.value}
                        className="rounded-md bg-muted/30 px-3 py-2"
                      >
                        <p className="text-sm text-foreground">{sub.label}</p>
                        <p className="font-mono text-xs text-muted-foreground">
                          {sub.value}
                        </p>
                      </div>
                    ))}
                    {typeSubtypes.length === 0 && (
                      <p className="col-span-2 py-4 text-center text-sm text-muted-foreground">
                        No subtypes found.
                      </p>
                    )}
                  </div>
                </CardContent>
              )}
            </Card>
          );
        })}
      </div>
    </div>
  );
}
