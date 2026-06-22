import { useState, useCallback, useRef } from 'react'

interface FileDropZoneProps {
  onFilesDropped: (files: File[]) => void
  submitting: boolean
}

const ACCEPTED_TYPES: Record<string, string> = {
  'application/pdf': 'PDF',
  'image/png': 'PNG',
  'image/jpeg': 'JPEG',
  'image/webp': 'WebP',
  'image/tiff': 'TIFF',
  'text/csv': 'CSV',
  'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet': 'XLSX',
  'application/vnd.ms-excel': 'XLS',
  'application/vnd.openxmlformats-officedocument.wordprocessingml.document': 'DOCX',
  'text/plain': 'TXT',
  'message/rfc822': 'EML',
}

const ACCEPTED_EXTS = ['.pdf', '.png', '.jpg', '.jpeg', '.webp', '.tiff', '.csv', '.xlsx', '.xls', '.docx', '.txt', '.eml']

export default function FileDropZone({ onFilesDropped, submitting }: FileDropZoneProps) {
  const [dragging, setDragging] = useState(false)
  const [dragCount, setDragCount] = useState(0)
  const inputRef = useRef<HTMLInputElement>(null)

  const handleDragEnter = useCallback((e: React.DragEvent) => {
    e.preventDefault()
    setDragCount(c => c + 1)
    setDragging(true)
  }, [])

  const handleDragLeave = useCallback((e: React.DragEvent) => {
    e.preventDefault()
    setDragCount(c => {
      const next = c - 1
      if (next <= 0) setDragging(false)
      return next
    })
  }, [])

  const handleDragOver = useCallback((e: React.DragEvent) => {
    e.preventDefault()
    e.dataTransfer.dropEffect = 'copy'
  }, [])

  const handleDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault()
    setDragging(false)
    setDragCount(0)
    const files = Array.from(e.dataTransfer.files).filter(f => isAccepted(f))
    if (files.length > 0) onFilesDropped(files)
  }, [onFilesDropped])

  const handleClick = () => inputRef.current?.click()

  const handleInputChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = Array.from(e.target.files || [])
    if (files.length > 0) onFilesDropped(files)
    e.target.value = ''
  }

  return (
    <div
      onDragEnter={handleDragEnter}
      onDragLeave={handleDragLeave}
      onDragOver={handleDragOver}
      onDrop={handleDrop}
      onClick={handleClick}
      className={`
        relative border-2 border-dashed rounded-lg px-4 py-3 cursor-pointer transition-all duration-200
        flex items-center gap-3
        ${dragging
          ? 'border-accent-blue bg-accent-blue/10 scale-[1.01]'
          : 'border-border-default hover:border-border-strong hover:bg-white/[0.02]'
        }
        ${submitting ? 'opacity-50 pointer-events-none' : ''}
      `}
    >
      <input
        ref={inputRef}
        type="file"
        multiple
        accept={ACCEPTED_EXTS.join(',')}
        onChange={handleInputChange}
        className="hidden"
      />

      <div className={`shrink-0 text-lg transition-transform ${dragging ? 'scale-110' : ''}`}>
        {dragging ? '📂' : '📁'}
      </div>

      <div className="flex-1 min-w-0">
        {dragging ? (
          <div className="text-xs font-medium text-accent-blue">Drop to process</div>
        ) : (
          <>
            <div className="text-xs text-text-secondary">Drop files or click to browse</div>
            <div className="text-[10px] text-text-muted mt-0.5">
              {ACCEPTED_EXTS.join(' ')}
            </div>
          </>
        )}
      </div>

      {dragging && (
        <div className="absolute inset-0 rounded-lg border-2 border-accent-blue animate-pulse pointer-events-none" />
      )}
    </div>
  )
}

function isAccepted(file: File): boolean {
  if (ACCEPTED_TYPES[file.type]) return true
  const ext = '.' + file.name.split('.').pop()?.toLowerCase()
  return ACCEPTED_EXTS.includes(ext)
}
