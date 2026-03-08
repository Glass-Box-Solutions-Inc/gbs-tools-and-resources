// @Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology
import { X, CheckCircle, AlertCircle, Info } from 'lucide-react'
import { useUIStore } from '../../stores/uiStore'

const icons = {
  success: <CheckCircle className="w-5 h-5 text-green-500" />,
  error: <AlertCircle className="w-5 h-5 text-red-500" />,
  info: <Info className="w-5 h-5 text-teal-500" />,
}

const bgStyles = {
  success: 'border-green-200 bg-green-50',
  error: 'border-red-200 bg-red-50',
  info: 'border-teal-200 bg-teal-50',
}

export function ToastContainer() {
  const { toasts, removeToast } = useUIStore()

  if (toasts.length === 0) return null

  return (
    <div className="fixed bottom-4 right-4 z-50 flex flex-col gap-2">
      {toasts.map((toast) => (
        <div
          key={toast.id}
          className={`flex items-center gap-3 px-4 py-3 rounded-xl border shadow-lg animate-in slide-in-from-right ${bgStyles[toast.type]}`}
        >
          {icons[toast.type]}
          <p className="text-sm text-gray-700 flex-1">{toast.message}</p>
          <button onClick={() => removeToast(toast.id)} className="p-1 hover:bg-white/50 rounded-lg transition-colors">
            <X className="w-4 h-4 text-gray-400" />
          </button>
        </div>
      ))}
    </div>
  )
}
