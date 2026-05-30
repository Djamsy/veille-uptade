export function SkeletonCard() {
  return (
    <div className="glass-card-static p-4">
      <div className="flex items-center justify-between mb-3">
        <div className="skeleton h-2.5 w-20" />
        <div className="skeleton h-5 w-5 rounded-full" />
      </div>
      <div className="skeleton h-8 w-16 mb-2" />
      <div className="skeleton h-1.5 w-full mb-2 rounded-full" />
      <div className="skeleton h-2 w-24" />
    </div>
  )
}

export function SkeletonWidget() {
  return (
    <div className="glass-card-static p-5">
      <div className="flex items-center justify-between mb-2">
        <div className="skeleton h-2.5 w-24" />
        <div className="skeleton h-5 w-5 rounded-full" />
      </div>
      <div className="skeleton h-2 w-40 mb-4" />
      <div className="space-y-3">
        <div className="skeleton h-3 w-full" />
        <div className="skeleton h-3 w-4/5" />
        <div className="skeleton h-3 w-3/5" />
        <div className="skeleton h-3 w-4/5" />
      </div>
    </div>
  )
}
