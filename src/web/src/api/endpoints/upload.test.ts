import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { uploadApi } from './upload'
import { ApiError } from '../client'

// Mock the api client
vi.mock('../client', async () => {
  const actual = await vi.importActual('../client')
  return {
    ...actual,
    api: {
      post: vi.fn(),
    },
  }
})

// Import the mocked api
import { api } from '../client'

describe('uploadApi', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  describe('initiate', () => {
    it('calls API with correct parameters', async () => {
      const mockResponse = {
        documentId: 1,
        uploadUrl: 'https://minio.example.com/upload',
        expiresIn: 3600,
        storagePath: '1/upload_abc/test.pdf',
      }
      vi.mocked(api.post).mockResolvedValueOnce(mockResponse)

      const result = await uploadApi.initiate({
        filename: 'test.pdf',
        contentType: 'application/pdf',
        size: 1024,
      })

      expect(api.post).toHaveBeenCalledWith('/documents/upload/initiate', {
        filename: 'test.pdf',
        contentType: 'application/pdf',
        size: 1024,
      })
      expect(result).toEqual(mockResponse)
    })

    it('throws on API error', async () => {
      vi.mocked(api.post).mockRejectedValueOnce(
        new ApiError(422, 'Unprocessable Content', { error: 'Invalid type' })
      )

      await expect(
        uploadApi.initiate({
          filename: 'test.exe',
          contentType: 'application/x-executable',
          size: 1024,
        })
      ).rejects.toThrow(ApiError)
    })
  })

  describe('complete', () => {
    it('calls API with document ID', async () => {
      const mockDocument = {
        id: 1,
        title: 'test.pdf',
        status: 'pending',
      }
      vi.mocked(api.post).mockResolvedValueOnce(mockDocument)

      const result = await uploadApi.complete({ documentId: 1 })

      expect(api.post).toHaveBeenCalledWith('/documents/upload/complete', {
        documentId: 1,
      })
      expect(result).toEqual(mockDocument)
    })
  })

  describe('abort', () => {
    it('calls API with document ID', async () => {
      const mockResponse = { success: true }
      vi.mocked(api.post).mockResolvedValueOnce(mockResponse)

      const result = await uploadApi.abort({ documentId: 1 })

      expect(api.post).toHaveBeenCalledWith('/documents/upload/abort', {
        documentId: 1,
      })
      expect(result).toEqual(mockResponse)
    })
  })

  describe('uploadFile', () => {
    let mockXHR: {
      open: ReturnType<typeof vi.fn>
      send: ReturnType<typeof vi.fn>
      setRequestHeader: ReturnType<typeof vi.fn>
      upload: { addEventListener: ReturnType<typeof vi.fn> }
      addEventListener: ReturnType<typeof vi.fn>
      status: number
      statusText: string
    }

    beforeEach(() => {
      mockXHR = {
        open: vi.fn(),
        send: vi.fn(),
        setRequestHeader: vi.fn(),
        upload: {
          addEventListener: vi.fn(),
        },
        addEventListener: vi.fn(),
        status: 200,
        statusText: 'OK',
      }

      vi.stubGlobal('XMLHttpRequest', vi.fn(() => mockXHR))
    })

    afterEach(() => {
      vi.unstubAllGlobals()
    })

    it('completes full upload flow successfully', async () => {
      const file = new File(['content'], 'test.pdf', { type: 'application/pdf' })

      // Mock initiate
      vi.mocked(api.post).mockResolvedValueOnce({
        documentId: 1,
        uploadUrl: 'https://minio.example.com/upload',
        expiresIn: 3600,
        storagePath: '1/upload_abc/test.pdf',
      })

      // Mock complete
      const mockDocument = {
        id: 1,
        title: 'test.pdf',
        status: 'pending',
      }
      vi.mocked(api.post).mockResolvedValueOnce(mockDocument)

      // Simulate XHR success when send is called
      mockXHR.send.mockImplementation(() => {
        const loadHandler = mockXHR.addEventListener.mock.calls.find(
          (call) => call[0] === 'load'
        )?.[1]
        if (loadHandler) {
          loadHandler()
        }
      })

      const result = await uploadApi.uploadFile(file)

      expect(result).toEqual(mockDocument)
      expect(mockXHR.open).toHaveBeenCalledWith('PUT', 'https://minio.example.com/upload')
      expect(mockXHR.setRequestHeader).toHaveBeenCalledWith('Content-Type', 'application/pdf')
    })

    it('tracks upload progress', async () => {
      const file = new File(['content'], 'test.pdf', { type: 'application/pdf' })
      const progressCallback = vi.fn()

      // Mock initiate
      vi.mocked(api.post).mockResolvedValueOnce({
        documentId: 1,
        uploadUrl: 'https://minio.example.com/upload',
        expiresIn: 3600,
        storagePath: '1/upload_abc/test.pdf',
      })

      // Mock complete
      vi.mocked(api.post).mockResolvedValueOnce({
        id: 1,
        title: 'test.pdf',
        status: 'pending',
      })

      // Simulate XHR with progress
      mockXHR.send.mockImplementation(() => {
        // Trigger progress event
        const progressHandler = mockXHR.upload.addEventListener.mock.calls.find(
          (call) => call[0] === 'progress'
        )?.[1]
        if (progressHandler) {
          progressHandler({ lengthComputable: true, loaded: 512, total: 1024 })
        }

        // Trigger load event
        const loadHandler = mockXHR.addEventListener.mock.calls.find(
          (call) => call[0] === 'load'
        )?.[1]
        if (loadHandler) {
          loadHandler()
        }
      })

      await uploadApi.uploadFile(file, progressCallback)

      expect(progressCallback).toHaveBeenCalledWith({
        loaded: 512,
        total: 1024,
        percent: 50,
      })
    })

    it('aborts upload on XHR error', async () => {
      const file = new File(['content'], 'test.pdf', { type: 'application/pdf' })

      // Mock initiate
      vi.mocked(api.post).mockResolvedValueOnce({
        documentId: 1,
        uploadUrl: 'https://minio.example.com/upload',
        expiresIn: 3600,
        storagePath: '1/upload_abc/test.pdf',
      })

      // Mock abort
      vi.mocked(api.post).mockResolvedValueOnce({ success: true })

      // Simulate XHR error
      mockXHR.send.mockImplementation(() => {
        const errorHandler = mockXHR.addEventListener.mock.calls.find(
          (call) => call[0] === 'error'
        )?.[1]
        if (errorHandler) {
          errorHandler()
        }
      })

      await expect(uploadApi.uploadFile(file)).rejects.toThrow('Network error during upload')

      // Verify abort was called
      expect(api.post).toHaveBeenCalledWith('/documents/upload/abort', { documentId: 1 })
    })

    it('aborts upload on HTTP error', async () => {
      const file = new File(['content'], 'test.pdf', { type: 'application/pdf' })

      // Mock initiate
      vi.mocked(api.post).mockResolvedValueOnce({
        documentId: 1,
        uploadUrl: 'https://minio.example.com/upload',
        expiresIn: 3600,
        storagePath: '1/upload_abc/test.pdf',
      })

      // Mock abort
      vi.mocked(api.post).mockResolvedValueOnce({ success: true })

      // Simulate XHR with 500 error
      mockXHR.status = 500
      mockXHR.statusText = 'Internal Server Error'
      mockXHR.send.mockImplementation(() => {
        const loadHandler = mockXHR.addEventListener.mock.calls.find(
          (call) => call[0] === 'load'
        )?.[1]
        if (loadHandler) {
          loadHandler()
        }
      })

      await expect(uploadApi.uploadFile(file)).rejects.toThrow('500')
    })

    it('uses application/octet-stream for unknown file types', async () => {
      const file = new File(['content'], 'test', { type: '' })

      // Mock initiate
      vi.mocked(api.post).mockResolvedValueOnce({
        documentId: 1,
        uploadUrl: 'https://minio.example.com/upload',
        expiresIn: 3600,
        storagePath: '1/upload_abc/test',
      })

      // Mock complete
      vi.mocked(api.post).mockResolvedValueOnce({
        id: 1,
        title: 'test',
        status: 'pending',
      })

      mockXHR.send.mockImplementation(() => {
        const loadHandler = mockXHR.addEventListener.mock.calls.find(
          (call) => call[0] === 'load'
        )?.[1]
        if (loadHandler) {
          loadHandler()
        }
      })

      await uploadApi.uploadFile(file)

      expect(api.post).toHaveBeenCalledWith('/documents/upload/initiate', {
        filename: 'test',
        contentType: 'application/octet-stream',
        size: 7, // 'content'.length
      })
    })
  })
})
