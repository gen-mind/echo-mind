import { useCallback, useRef, useState } from 'react'
import { Upload, X, FileText, AlertCircle, CheckCircle2 } from 'lucide-react'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  Button,
  Progress,
} from '@/components/ui'
import {
  useFileUpload,
  formatFileSize,
  getFileTypeName,
} from '@/hooks'
import { cn } from '@/lib/utils'
import type { Document } from '@/models'

interface FileUploadDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  onUploadComplete?: (document: Document) => void
}

export function FileUploadDialog({
  open,
  onOpenChange,
  onUploadComplete,
}: FileUploadDialogProps) {
  const fileInputRef = useRef<HTMLInputElement>(null)
  const [isDragging, setIsDragging] = useState(false)

  const {
    status,
    progress,
    error,
    selectedFile,
    uploadedDocument,
    selectFile,
    startUpload,
    reset,
    isUploading,
    isValidFile,
  } = useFileUpload({
    onSuccess: (document) => {
      onUploadComplete?.(document)
    },
  })

  const handleClose = useCallback(() => {
    if (!isUploading) {
      reset()
      onOpenChange(false)
    }
  }, [isUploading, reset, onOpenChange])

  const handleFileSelect = useCallback(
    (event: React.ChangeEvent<HTMLInputElement>) => {
      const file = event.target.files?.[0]
      if (file) {
        selectFile(file)
      }
      // Reset input so same file can be selected again
      event.target.value = ''
    },
    [selectFile]
  )

  const handleDrop = useCallback(
    (event: React.DragEvent) => {
      event.preventDefault()
      setIsDragging(false)

      const file = event.dataTransfer.files?.[0]
      if (file) {
        selectFile(file)
      }
    },
    [selectFile]
  )

  const handleDragOver = useCallback((event: React.DragEvent) => {
    event.preventDefault()
    setIsDragging(true)
  }, [])

  const handleDragLeave = useCallback((event: React.DragEvent) => {
    event.preventDefault()
    setIsDragging(false)
  }, [])

  const handleUpload = useCallback(async () => {
    await startUpload()
  }, [startUpload])

  const handleSelectAnother = useCallback(() => {
    reset()
  }, [reset])

  const handleBrowseClick = useCallback(() => {
    fileInputRef.current?.click()
  }, [])

  return (
    <Dialog open={open} onOpenChange={handleClose}>
      <DialogContent className="sm:max-w-[500px]">
        <DialogHeader>
          <DialogTitle>Upload Document</DialogTitle>
          <DialogDescription>
            Upload a file to add it to your documents. Supported formats include
            PDF, Word, Excel, images, audio, and video.
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-4 py-4">
          {/* Success state */}
          {status === 'success' && uploadedDocument && (
            <div className="flex flex-col items-center gap-4 py-8">
              <div className="rounded-full bg-green-100 p-3 dark:bg-green-900">
                <CheckCircle2 className="h-8 w-8 text-green-600 dark:text-green-400" />
              </div>
              <div className="text-center">
                <p className="font-medium">Upload complete!</p>
                <p className="text-sm text-muted-foreground mt-1">
                  {uploadedDocument.title || selectedFile?.name}
                </p>
              </div>
              <Button onClick={handleSelectAnother} variant="outline">
                Upload another file
              </Button>
            </div>
          )}

          {/* Drop zone */}
          {status !== 'success' && (
            <>
              <div
                role="region"
                aria-label="File drop zone"
                className={cn(
                  'border-2 border-dashed rounded-lg p-8 text-center transition-colors',
                  isDragging
                    ? 'border-primary bg-primary/5'
                    : 'border-muted-foreground/25 hover:border-muted-foreground/50',
                  isUploading && 'pointer-events-none opacity-50'
                )}
                onDrop={handleDrop}
                onDragOver={handleDragOver}
                onDragLeave={handleDragLeave}
              >
                <input
                  ref={fileInputRef}
                  type="file"
                  aria-label="File upload input"
                  className="hidden"
                  onChange={handleFileSelect}
                  accept=".pdf,.doc,.docx,.xls,.xlsx,.ppt,.pptx,.txt,.md,.csv,.html,.jpg,.jpeg,.png,.gif,.webp,.mp3,.wav,.ogg,.webm,.mp4"
                  disabled={isUploading}
                />

                {!selectedFile ? (
                  <>
                    <Upload className="h-10 w-10 mx-auto text-muted-foreground mb-4" />
                    <p className="text-sm font-medium mb-1">
                      Drag and drop your file here
                    </p>
                    <p className="text-xs text-muted-foreground mb-4">
                      or click to browse
                    </p>
                    <Button
                      type="button"
                      variant="secondary"
                      onClick={handleBrowseClick}
                      disabled={isUploading}
                    >
                      Browse files
                    </Button>
                  </>
                ) : (
                  <div className="flex items-center gap-3">
                    <div className="flex-shrink-0 p-2 bg-muted rounded">
                      <FileText className="h-8 w-8 text-muted-foreground" />
                    </div>
                    <div className="flex-1 min-w-0 text-left">
                      <p className="font-medium truncate">{selectedFile.name}</p>
                      <p className="text-sm text-muted-foreground">
                        {getFileTypeName(selectedFile.type)} &bull;{' '}
                        {formatFileSize(selectedFile.size)}
                      </p>
                    </div>
                    {!isUploading && (
                      <Button
                        type="button"
                        variant="ghost"
                        size="icon"
                        aria-label="Clear selected file"
                        onClick={() => selectFile(null)}
                      >
                        <X className="h-4 w-4" />
                      </Button>
                    )}
                  </div>
                )}
              </div>

              {/* Progress bar */}
              {isUploading && progress && (
                <div className="space-y-2">
                  <Progress value={progress.percent} />
                  <div className="flex justify-between text-sm text-muted-foreground">
                    <span>
                      {status === 'completing'
                        ? 'Finalizing...'
                        : `Uploading... ${progress.percent}%`}
                    </span>
                    <span>
                      {formatFileSize(progress.loaded)} / {formatFileSize(progress.total)}
                    </span>
                  </div>
                </div>
              )}

              {/* Error message */}
              {error && (
                <div className="flex items-start gap-2 p-3 bg-destructive/10 border border-destructive/20 rounded-lg">
                  <AlertCircle className="h-5 w-5 text-destructive flex-shrink-0 mt-0.5" />
                  <div>
                    <p className="text-sm font-medium text-destructive">
                      Upload failed
                    </p>
                    <p className="text-sm text-destructive/80">
                      {'message' in error ? error.message : String(error)}
                    </p>
                  </div>
                </div>
              )}
            </>
          )}
        </div>

        {status !== 'success' && (
          <DialogFooter>
            <Button variant="outline" onClick={handleClose} disabled={isUploading}>
              Cancel
            </Button>
            <Button
              onClick={handleUpload}
              disabled={!isValidFile || isUploading}
            >
              {isUploading ? 'Uploading...' : 'Upload'}
            </Button>
          </DialogFooter>
        )}

        {status === 'success' && (
          <DialogFooter>
            <Button onClick={handleClose}>Done</Button>
          </DialogFooter>
        )}
      </DialogContent>
    </Dialog>
  )
}
