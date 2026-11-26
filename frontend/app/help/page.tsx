"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { useForm } from "react-hook-form";
import { z } from "zod";

import { AppLayout } from "@/components/layout/AppLayout";
import { Button } from "@/components/ui/Button";
import { EmptyState } from "@/components/ui/EmptyState";
import { Input, Select, Textarea } from "@/components/ui/FormFields";
import { TableSkeleton } from "@/components/ui/Skeleton";
import { SimpleStatusBadge } from "@/components/ui/StatusBadge";
import { apiRequest, emitToast } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { formatDateTime } from "@/lib/format";
import type { ComplaintListResponse, DocumentListResponse } from "@/lib/types";

const complaintSchema = z.object({
  subject: z.string().trim().min(3, "Subject must be 3–120 characters.").max(120),
  category: z.enum(["bug", "account", "privacy", "other"]),
  message: z.string().trim().min(10, "Message must be 10–4000 characters.").max(4000),
  document_id: z.string().optional(),
});

type ComplaintFormValues = z.infer<typeof complaintSchema>;

function HelpContent() {
  const { user } = useAuth();
  const queryClient = useQueryClient();

  const { data: complaints, isLoading, isError, refetch } = useQuery<ComplaintListResponse>({
    queryKey: ["complaints", "mine"],
    queryFn: () => apiRequest<ComplaintListResponse>("/complaints?page=1&page_size=20"),
  });

  const { data: myDocs } = useQuery<DocumentListResponse>({
    queryKey: ["documents", "for-help"],
    queryFn: () => apiRequest<DocumentListResponse>("/documents?page=1&page_size=50"),
    enabled: user?.role === "doctor",
  });

  const {
    register,
    reset,
    handleSubmit,
    formState: { errors },
  } = useForm<ComplaintFormValues>({
    resolver: zodResolver(complaintSchema),
    defaultValues: { category: "bug", document_id: "" },
  });

  const createMutation = useMutation({
    mutationFn: (values: ComplaintFormValues) =>
      apiRequest("/complaints", {
        method: "POST",
        body: {
          subject: values.subject,
          category: values.category,
          message: values.message,
          document_id: values.document_id ? values.document_id : null,
        },
      }),
    onSuccess: () => {
      emitToast({ kind: "success", message: "Complaint submitted." });
      reset({ subject: "", category: "bug", message: "", document_id: "" });
      queryClient.invalidateQueries({ queryKey: ["complaints", "mine"] });
    },
  });

  return (
    <div className="space-y-12">
      <section className="max-w-form">
        <h1 className="text-[28px] font-semibold text-text">Help</h1>
        <p className="mt-1 text-sm text-text-muted">
          Report a bug, account restriction question, or privacy concern. Do not include real
          patient names. You can also email{" "}
          <a href="mailto:support@joggo.app" className="font-medium text-accent hover:underline">
            support@joggo.app
          </a>
          .
        </p>

        <form
          onSubmit={handleSubmit((vals) => createMutation.mutate(vals))}
          className="mt-6 space-y-4"
          noValidate
        >
          <Input
            id="help-subject"
            label="Subject"
            error={errors.subject?.message}
            {...register("subject")}
          />

          <Select
            id="help-category"
            label="Category"
            error={errors.category?.message}
            {...register("category")}
          >
            <option value="bug">Bug</option>
            <option value="account">Account</option>
            <option value="privacy">Privacy</option>
            <option value="other">Other</option>
          </Select>

          {user?.role === "doctor" && (
            <Select id="help-doc" label="Related document (optional)" {...register("document_id")}>
              <option value="">None</option>
              {myDocs?.items.map((d) => (
                <option key={d.id} value={d.id}>
                  {d.original_filename}
                </option>
              ))}
            </Select>
          )}

          <Textarea
            id="help-message"
            label="Message"
            error={errors.message?.message}
            {...register("message")}
          />

          <Button type="submit" loading={createMutation.isPending}>
            Submit complaint
          </Button>
        </form>
      </section>

      <section className="border-t border-border pt-8">
        <h2 className="mb-4 text-xl font-semibold text-text">My complaints</h2>

        {isLoading ? (
          <TableSkeleton rows={4} />
        ) : isError ? (
          <div className="rounded bg-danger-tint p-4 text-sm text-danger">
            Could not load complaints.{" "}
            <button type="button" onClick={() => refetch()} className="font-medium underline">
              Try again
            </button>
          </div>
        ) : !complaints || complaints.items.length === 0 ? (
          <EmptyState message="You have not filed any complaints." />
        ) : (
          <div className="overflow-x-auto">
            <table aria-label="My complaints" className="w-full border-collapse text-left text-sm">
              <thead>
                <tr className="border-y border-border bg-bg-subtle text-xs font-medium text-text-muted">
                  <th className="px-3 py-2.5">Subject</th>
                  <th className="px-3 py-2.5">Status</th>
                  <th className="px-3 py-2.5">Updated</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border">
                {complaints.items.map((c) => (
                  <tr key={c.id} className="hover:bg-bg-subtle">
                    <td className="px-3 py-3 font-medium text-text">
                      <Link href={`/help/${c.id}`} className="hover:text-accent hover:underline">
                        {c.subject}
                      </Link>
                    </td>
                    <td className="px-3 py-3">
                      <SimpleStatusBadge status={c.status} kind="complaint" />
                    </td>
                    <td className="px-3 py-3 text-text-muted">{formatDateTime(c.updated_at)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </div>
  );
}

export default function HelpPage() {
  return (
    <AppLayout allowedRoles={["doctor", "auditor"]}>
      <HelpContent />
    </AppLayout>
  );
}
