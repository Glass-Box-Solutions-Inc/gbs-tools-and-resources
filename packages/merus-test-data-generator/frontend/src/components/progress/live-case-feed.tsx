"use client";

import { useRef, useEffect } from "react";
import { Badge } from "@/components/ui/badge";
import { capitalize, stageColor } from "@/lib/utils";

export interface FeedItem {
  id: string;
  type: "case" | "doc" | "phase" | "error";
  message: string;
  stage?: string;
  timestamp: Date;
}

interface LiveCaseFeedProps {
  items: FeedItem[];
}

export function LiveCaseFeed({ items }: LiveCaseFeedProps) {
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (containerRef.current) {
      containerRef.current.scrollTop = containerRef.current.scrollHeight;
    }
  }, [items]);

  return (
    <div className="rounded-lg border border-border bg-white">
      <div className="border-b border-border px-4 py-3">
        <h3 className="text-sm font-medium text-foreground">Live Feed</h3>
      </div>
      <div
        ref={containerRef}
        className="scrollbar-thin h-80 overflow-y-auto p-4"
      >
        {items.length === 0 && (
          <p className="py-8 text-center text-sm text-muted-foreground">
            Waiting for events...
          </p>
        )}
        <div className="space-y-2">
          {items.map((item) => (
            <div
              key={item.id}
              className="flex items-start gap-3 rounded-md px-3 py-2 text-sm hover:bg-muted/30"
            >
              <span className="shrink-0 text-xs tabular-nums text-muted-foreground">
                {item.timestamp.toLocaleTimeString()}
              </span>
              <span className="flex-1 text-foreground">{item.message}</span>
              {item.stage && (
                <Badge
                  variant="secondary"
                  className={stageColor(item.stage)}
                >
                  {capitalize(item.stage)}
                </Badge>
              )}
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
