// @Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology

interface QuickChipsProps {
  chips: string[]
  onSelect: (chip: string) => void
  disabled?: boolean
}

/**
 * Quick-reply pill buttons rendered below the message list.
 * Clicking a chip sends that value as the user's next message.
 */
export function QuickChips({ chips, onSelect, disabled }: QuickChipsProps) {
  if (!chips.length) return null

  return (
    <div className="flex flex-wrap gap-2 px-4 py-2 border-t border-gray-100">
      {chips.map((chip) => (
        <button
          key={chip}
          onClick={() => onSelect(chip)}
          disabled={disabled}
          className="px-3 py-1.5 text-sm bg-teal-50 text-teal-700 border border-teal-200 rounded-full hover:bg-teal-100 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
          type="button"
        >
          {chip}
        </button>
      ))}
    </div>
  )
}
