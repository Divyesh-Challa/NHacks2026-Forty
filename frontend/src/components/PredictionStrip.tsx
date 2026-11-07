// Predicted phrases from POST /predict. Suggestions only — never auto-spoken. Owner: Role C/D.
export function PredictionStrip({ phrases }: { phrases: string[] }) {
  if (!phrases.length) return null
  return (
    <div className="predictions">
      {phrases.map((p) => <span key={p} className="chip">{p}</span>)}
    </div>
  )
}
