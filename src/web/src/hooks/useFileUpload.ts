import { useState, useCallback, useRef } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { uploadApi, type UploadProgress } from '@/api'
import type { Document } from '@/models'

// Allowed file types matching backend validation
const ALLOWED_CONTENT_TYPES = new Set([
  // Documents
  'application/pdf',
  'application/msword',
  'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
  'application/vnd.ms-excel',
  'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
  'application/vnd.ms-powerpoint',
  'application/vnd.openxmlformats-officedocument.presentationml.presentation',
  // Text
  'text/plain',
  'text/markdown',
  'text/csv',
  'text/html',
  // Images
  'image/jpeg',
  'image/png',
  'image/gif',
  'image/webp',
  // Audio
  'audio/mpeg',
  'audio/wav',
  'audio/ogg',
  'audio/webm',
  // Video
  'video/mp4',
  'video/webm',
  'video/ogg',
])

// Maximum file size (5GB)
const MAX_FILE_SIZE = 5 * 1024 * 1024 * 1024

export type UploadStatus = 'idle' | 'validating' | 'uploading' | 'completing' | 'success' | 'error'

export interface FileValidationError {
  type: 'invalid_type' | 'file_too_large' | 'no_file'
  message: string
}

export interface UseFileUploadOptions {
  onSuccess?: (document: Document) => void
  onError?: (error: Error) => void
}

export interface UseFileUploadResult {
  status: UploadStatus
  progress: UploadProgress | null
  error: Error | FileValidationError | null
  selectedFile: File | null
  uploadedDocument: Document | null
  selectFile: (file: File | null) => FileValidationError | null
  startUpload: () => Promise<void>
  cancelUpload: () => void
  reset: () => void
  isUploading: boolean
  isValidFile: boolean
}

/**
 * Hook for managing file uploads with validation and progress tracking.
 *
 * Usage:
 * ```tsx
 * const { selectFile, startUpload, progress, status } = useFileUpload({
 *   onSuccess: (doc) => console.log('Uploaded:', doc),
 * })
 *
 * const handleDrop = (file: File) => {
 *   const error = selectFile(file)
 *   if (!error) {
 *     startUpload()
 *   }
 * }
 * ```
 */
export function useFileUpload(options: UseFileUploadOptions = {}): UseFileUploadResult {
  const { onSuccess, onError } = options
  const queryClient = useQueryClient()

  const [status, setStatus] = useState<UploadStatus>('idle')
  const [progress, setProgress] = useState<UploadProgress | null>(null)
  const [error, setError] = useState<Error | FileValidationError | null>(null)
  const [selectedFile, setSelectedFile] = useState<File | null>(null)
  const [uploadedDocument, setUploadedDocument] = useState<Document | null>(null)

  // Ref for abort controller
  const abortControllerRef = useRef<AbortController | null>(null)

  /**
   * Validate and select a file for upload.
   */
  const selectFile = useCallback((file: File | null): FileValidationError | null => {
    setError(null)
    setUploadedDocument(null)

    if (!file) {
      setSelectedFile(null)
      setStatus('idle')
      return null
    }

    // Validate file type
    const fileType = file.type || 'application/octet-stream'
    if (!ALLOWED_CONTENT_TYPES.has(fileType)) {
      const validationError: FileValidationError = {
        type: 'invalid_type',
        message: `File type "${fileType}" is not supported. Please upload documents, images, audio, or video files.`,
      }
      setError(validationError)
      setSelectedFile(null)
      return validationError
    }

    // Validate file size
    if (file.size > MAX_FILE_SIZE) {
      const validationError: FileValidationError = {
        type: 'file_too_large',
        message: `File size exceeds the maximum allowed size of 5GB.`,
      }
      setError(validationError)
      setSelectedFile(null)
      return validationError
    }

    if (file.size === 0) {
      const validationError: FileValidationError = {
        type: 'file_too_large',
        message: `File is empty.`,
      }
      setError(validationError)
      setSelectedFile(null)
      return validationError
    }

    setSelectedFile(file)
    setStatus('idle')
    return null
  }, [])

  /**
   * Upload mutation using React Query.
   */
  const uploadMutation = useMutation({
    mutationFn: async (file: File) => {
      setStatus('uploading')
      setProgress({ loaded: 0, total: file.size, percent: 0 })

      const document = await uploadApi.uploadFile(file, (uploadProgress) => {
        setProgress(uploadProgress)
      })

      setStatus('completing')
      return document
    },
    onSuccess: (document) => {
      setStatus('success')
      setUploadedDocument(document)
      setProgress({ loaded: selectedFile?.size || 0, total: selectedFile?.size || 0, percent: 100 })
      queryClient.invalidateQueries({ queryKey: ['documents'] })
      onSuccess?.(document)
    },
    onError: (err: Error) => {
      setStatus('error')
      setError(err)
      onError?.(err)
    },
  })

  /**
   * Start the upload process.
   */
  const startUpload = useCallback(async () => {
    if (!selectedFile) {
      setError({ type: 'no_file', message: 'No file selected' })
      return
    }

    setError(null)
    setStatus('validating')

    try {
      await uploadMutation.mutateAsync(selectedFile)
    } catch {
      // Error is handled by mutation
    }
  }, [selectedFile, uploadMutation])

  /**
   * Cancel the current upload.
   */
  const cancelUpload = useCallback(() => {
    if (abortControllerRef.current) {
      abortControllerRef.current.abort()
      abortControllerRef.current = null
    }
    setStatus('idle')
    setProgress(null)
    setError(null)
  }, [])

  /**
   * Reset the upload state.
   */
  const reset = useCallback(() => {
    cancelUpload()
    setSelectedFile(null)
    setUploadedDocument(null)
    setStatus('idle')
    setProgress(null)
    setError(null)
  }, [cancelUpload])

  return {
    status,
    progress,
    error,
    selectedFile,
    uploadedDocument,
    selectFile,
    startUpload,
    cancelUpload,
    reset,
    isUploading: status === 'uploading' || status === 'completing' || status === 'validating',
    isValidFile: selectedFile !== null && error === null,
  }
}

/**
 * Format bytes to human-readable string.
 */
export function formatFileSize(bytes: number): string {
  if (bytes === 0) return '0 Bytes'

  const k = 1024
  const sizes = ['Bytes', 'KB', 'MB', 'GB']
  const i = Math.floor(Math.log(bytes) / Math.log(k))

  return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i]
}

/**
 * Get file extension from filename.
 */
export function getFileExtension(filename: string): string {
  const parts = filename.split('.')
  return parts.length > 1 ? parts.pop()?.toLowerCase() || '' : ''
}

/**
 * Get a friendly file type name from MIME type.
 */
export function getFileTypeName(mimeType: string): string {
  const typeMap: Record<string, string> = {
    'application/pdf': 'PDF',
    'application/msword': 'Word Document',
    'application/vnd.openxmlformats-officedocument.wordprocessingml.document': 'Word Document',
    'application/vnd.ms-excel': 'Excel Spreadsheet',
    'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet': 'Excel Spreadsheet',
    'application/vnd.ms-powerpoint': 'PowerPoint',
    'application/vnd.openxmlformats-officedocument.presentationml.presentation': 'PowerPoint',
    'text/plain': 'Text File',
    'text/markdown': 'Markdown',
    'text/csv': 'CSV',
    'text/html': 'HTML',
    'image/jpeg': 'JPEG Image',
    'image/png': 'PNG Image',
    'image/gif': 'GIF Image',
    'image/webp': 'WebP Image',
    'audio/mpeg': 'MP3 Audio',
    'audio/wav': 'WAV Audio',
    'audio/ogg': 'OGG Audio',
    'audio/webm': 'WebM Audio',
    'video/mp4': 'MP4 Video',
    'video/webm': 'WebM Video',
    'video/ogg': 'OGG Video',
  }

  return typeMap[mimeType] || 'File'
}
