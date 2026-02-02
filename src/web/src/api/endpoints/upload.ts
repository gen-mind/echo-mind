import { api, ApiError } from '../client'
import type { Document } from '@/models'

export interface InitiateUploadRequest {
  filename: string
  contentType: string
  size: number
}

export interface InitiateUploadResponse {
  documentId: number
  uploadUrl: string
  expiresIn: number
  storagePath: string
}

export interface CompleteUploadRequest {
  documentId: number
}

export interface AbortUploadRequest {
  documentId: number
}

export interface AbortUploadResponse {
  success: boolean
}

export interface UploadProgress {
  loaded: number
  total: number
  percent: number
}

export type ProgressCallback = (progress: UploadProgress) => void

/**
 * Upload a file to MinIO using a pre-signed URL with progress tracking.
 *
 * Uses XMLHttpRequest instead of fetch because fetch doesn't support
 * upload progress events.
 */
async function uploadToPresignedUrl(
  url: string,
  file: File,
  onProgress?: ProgressCallback
): Promise<void> {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest()

    xhr.upload.addEventListener('progress', (event) => {
      if (event.lengthComputable && onProgress) {
        onProgress({
          loaded: event.loaded,
          total: event.total,
          percent: Math.round((event.loaded / event.total) * 100),
        })
      }
    })

    xhr.addEventListener('load', () => {
      if (xhr.status >= 200 && xhr.status < 300) {
        resolve()
      } else {
        reject(new ApiError(xhr.status, xhr.statusText))
      }
    })

    xhr.addEventListener('error', () => {
      reject(new ApiError(0, 'Network error during upload'))
    })

    xhr.addEventListener('abort', () => {
      reject(new ApiError(0, 'Upload aborted'))
    })

    xhr.open('PUT', url)
    xhr.setRequestHeader('Content-Type', file.type)
    xhr.send(file)
  })
}

export const uploadApi = {
  /**
   * Initiate a file upload.
   *
   * Creates a document record and returns a pre-signed URL for direct upload.
   */
  initiate: (request: InitiateUploadRequest) =>
    api.post<InitiateUploadResponse>('/documents/upload/initiate', request),

  /**
   * Complete a file upload.
   *
   * Verifies the file exists in MinIO and triggers document processing.
   */
  complete: (request: CompleteUploadRequest) =>
    api.post<Document>('/documents/upload/complete', request),

  /**
   * Abort a file upload.
   *
   * Cleans up the document record and any uploaded data.
   */
  abort: (request: AbortUploadRequest) =>
    api.post<AbortUploadResponse>('/documents/upload/abort', request),

  /**
   * Upload a file with the complete three-step flow.
   *
   * 1. Initiates upload to get pre-signed URL
   * 2. Uploads file directly to MinIO with progress tracking
   * 3. Completes upload to trigger processing
   *
   * @param file - The file to upload
   * @param onProgress - Optional callback for upload progress
   * @returns The created document
   */
  uploadFile: async (
    file: File,
    onProgress?: ProgressCallback
  ): Promise<Document> => {
    // Step 1: Initiate upload
    const initResponse = await uploadApi.initiate({
      filename: file.name,
      contentType: file.type || 'application/octet-stream',
      size: file.size,
    })

    try {
      // Step 2: Upload to MinIO
      await uploadToPresignedUrl(initResponse.uploadUrl, file, onProgress)

      // Step 3: Complete upload
      const document = await uploadApi.complete({
        documentId: initResponse.documentId,
      })

      return document
    } catch (error) {
      // Clean up on failure
      try {
        await uploadApi.abort({ documentId: initResponse.documentId })
      } catch {
        // Ignore abort errors
      }
      throw error
    }
  },
}
