interface PhasePlaceholderProps {
  title: string
  phase: string
  description: string
}

export default function PhasePlaceholder({ title, phase, description }: PhasePlaceholderProps) {
  return (
    <div className="flex h-full items-center justify-center p-8">
      <div className="max-w-md rounded-2xl border border-gray-200 bg-white p-8 text-center shadow-sm">
        <span className="inline-block rounded-full bg-indigo-50 px-3 py-1 text-xs font-medium text-indigo-600">
          {phase}
        </span>
        <h2 className="mt-3 text-xl font-semibold">{title}</h2>
        <p className="mt-2 text-sm leading-relaxed text-gray-500">{description}</p>
      </div>
    </div>
  )
}
