// Predicted phrases from POST /predict. They also appear first on the top-level board,
// so picking one is a single selection. Suggestions only — never auto-spoken.
export function PredictionStrip({ phrases, loading }: { phrases: string[]; loading: boolean }) {
  if (!phrases.length && !loading) return null
  return (
    <div className="predictions" aria-label="Suggested phrases">
      <span className="tag">{loading ? 'Thinking…' : 'Suggested'}</span>
      {phrases.map((p) => (
        <span key={p} className="chip">{p}</span>
      ))}
    </div>
  )
}
