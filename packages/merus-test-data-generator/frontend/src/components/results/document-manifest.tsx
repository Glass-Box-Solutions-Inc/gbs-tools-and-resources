"use client";

import { FileText, CheckCircle2, XCircle } from "lucide-react";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { Badge } from "@/components/ui/badge";
import type { DocumentPreview } from "@/lib/api/types";
import { capitalize } from "@/lib/utils";

interface DocumentManifestProps {
  documents: DocumentPreview[];
  runId: number;
  caseId: string;
}

export function DocumentManifest({
  documents,
  runId,
  caseId,
}: DocumentManifestProps) {
  return (
    <div className="rounded-lg border border-border bg-white">
      <div className="border-b border-border px-4 py-3">
        <h3 className="text-sm font-medium text-foreground">
          Document Manifest ({documents.length} documents)
        </h3>
      </div>
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>Title</TableHead>
            <TableHead>Subtype</TableHead>
            <TableHead>Date</TableHead>
            <TableHead>PDF</TableHead>
            <TableHead className="w-12" />
          </TableRow>
        </TableHeader>
        <TableBody>
          {documents.map((doc, idx) => (
            <TableRow key={`${doc.filename}-${idx}`}>
              <TableCell className="font-medium">{doc.title}</TableCell>
              <TableCell>
                <Badge variant="secondary" className="bg-slate-100 text-slate-700">
                  {capitalize(doc.subtype)}
                </Badge>
              </TableCell>
              <TableCell className="text-muted-foreground">
                {doc.doc_date}
              </TableCell>
              <TableCell>
                {doc.pdf_generated ? (
                  <CheckCircle2 className="h-4 w-4 text-emerald-500" />
                ) : (
                  <XCircle className="h-4 w-4 text-slate-300" />
                )}
              </TableCell>
              <TableCell>
                {doc.pdf_generated && (
                  <a
                    href={`/api/preview/${runId}/documents/${caseId}/${doc.filename}`}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="text-primary hover:text-primary/80"
                    title="View PDF"
                  >
                    <FileText className="h-4 w-4" />
                  </a>
                )}
              </TableCell>
            </TableRow>
          ))}
          {documents.length === 0 && (
            <TableRow>
              <TableCell colSpan={5} className="py-8 text-center text-muted-foreground">
                No documents found.
              </TableCell>
            </TableRow>
          )}
        </TableBody>
      </Table>
    </div>
  );
}
