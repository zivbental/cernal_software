import { useState } from "react";
import { useAnnotations, useCreateAnnotation, useDeleteAnnotation } from "@/api/queries";
import type { DecisionTag } from "@/api/types";

/** Research notes record authors and dates; a shortlist does not authorize synthesis. */
export function CandidateReview({ candidateId }: { candidateId: string }) {
  const annotations = useAnnotations(candidateId);
  const create = useCreateAnnotation(candidateId);
  const remove = useDeleteAnnotation(candidateId);
  const [text, setText] = useState("");
  const [tag, setTag] = useState<DecisionTag>("NONE");
  return <section className="mt-4 rounded-xl border border-border p-4">
    <h3 className="text-sm font-semibold">Researcher review</h3>
    {annotations.isLoading && <p>Loading notes…</p>}
    {annotations.isError && <p role="alert">Could not load notes. <button onClick={() => annotations.refetch()}>Retry</button></p>}
    {annotations.data?.map((note) => <div key={note.id} className="my-2 border-b border-border pb-2 text-xs">
      <p>{note.decision_tag} · {note.author} · {new Date(note.created_at).toLocaleString()}</p>
      <p className="whitespace-pre-wrap">{note.text}</p>
      <button disabled={remove.isPending} onClick={() => remove.mutate(note.id)}>Delete note</button>
    </div>)}
    <form onSubmit={(event) => {
      event.preventDefault();
      create.mutate({ text, decision_tag: tag }, { onSuccess: () => setText("") });
    }}>
      <label className="mt-2 block text-xs">Review note<textarea aria-label="Review note" value={text} onChange={(event) => setText(event.target.value)} className="mt-1 w-full rounded border border-border bg-surface p-2" /></label>
      <label className="block text-xs">Decision<select aria-label="Review decision" value={tag} onChange={(event) => setTag(event.target.value as DecisionTag)} className="m-2 rounded border border-border bg-surface p-2">
        <option value="NONE">Note</option><option value="PINNED">Pinned</option><option value="SHORTLISTED">Shortlisted</option><option value="REJECTED">Rejected in review</option>
      </select></label>
      <button type="submit" disabled={create.isPending || (!text.trim() && tag === "NONE")}>Save review</button>
      {(create.isError || remove.isError) && <p role="alert">Could not save this change. Your note is retained; please retry.</p>}
    </form>
  </section>;
}
