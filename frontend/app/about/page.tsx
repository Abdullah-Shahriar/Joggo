import { PublicLayout } from "@/components/layout/PublicLayout";
import { APP_NAME } from "@/lib/constants";

export default function AboutPage() {
  return (
    <PublicLayout>
      <article className="mx-auto max-w-prose px-4 py-16 sm:px-6">
        <h1 className="text-[28px] font-semibold text-text">About {APP_NAME}</h1>

        <section className="mt-8 space-y-3">
          <h2 className="text-xl font-semibold text-text">What it is</h2>
          <p className="text-[15px] leading-relaxed text-text">
            {APP_NAME} is a privacy-first gateway that lets clinicians use modern language models to
            draft discharge summaries, case summaries, and treatment plans without sending real
            patient identities to external AI providers.
          </p>
          <p className="text-[15px] leading-relaxed text-text">
            Every PDF is extracted, scanned, and tokenized locally on the server. Only sanitized
            text containing context-preserving placeholders leaves the system, and real details are
            restored locally in the clinician&apos;s browser session.
          </p>
        </section>

        <section className="mt-10 space-y-3 border-t border-border pt-8">
          <h2 className="text-xl font-semibold text-text">The problem</h2>
          <p className="text-[15px] leading-relaxed text-text">
            Hospitals often ban cloud AI tools completely, which pushes busy staff toward unmanaged
            shadow AI. On the other hand, blunt redaction replaces everything with generic blocks
            and removes the dates, ages, and timelines that clinical writing depends on.
          </p>
          <p className="text-[15px] leading-relaxed text-text">
            Clinical PDFs also conceal sensitive data beyond visible paragraphs: author metadata,
            annotations, form fields, and scanned headers or images frequently contain patient names
            and phone numbers.
          </p>
        </section>

        <section className="mt-10 space-y-3 border-t border-border pt-8">
          <h2 className="text-xl font-semibold text-text">Our approach</h2>
          <p className="text-[15px] leading-relaxed text-text">
            We run local text extraction, OCR, rule-based and local NLP detection across the HIPAA
            18 identifiers, followed by an independent safety scan and mandatory clinician review.
            Real values stay exclusively in an AES-256-GCM encrypted in-memory vault tied to the
            session and are never written to PostgreSQL or logs.
          </p>
          <p className="text-[15px] leading-relaxed text-text">
            Every authentication event, access check, document transition, and administrative action
            is recorded in an append-only, hash-chained audit log.
          </p>
        </section>

        <section className="mt-10 space-y-3 border-t border-border pt-8">
          <h2 className="text-xl font-semibold text-text">Limits</h2>
          <p className="text-[15px] leading-relaxed text-text">
            Automated identifier detection combines rules with a small local model and is never
            perfect. For that reason, a clinician always reviews the cleaned text and can highlight
            any remaining item to replace it everywhere before approving generation.
          </p>
          <p className="text-[15px] leading-relaxed text-text">
            This deployment is a demonstration environment. Use synthetic clinical records only.
          </p>
        </section>
      </article>
    </PublicLayout>
  );
}
