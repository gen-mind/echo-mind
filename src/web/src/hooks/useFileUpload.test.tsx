import { describe, it, expect, vi, beforeEach } from 'vitest'
import { renderHook, act, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import type { ReactNode } from 'react'
import { useFileUpload, formatFileSize, getFileExtension, getFileTypeName } from './useFileUpload'

// Mock the upload API
vi.mock('@/api', () => ({
  uploadApi: {
    uploadFile: vi.fn(),
  },
}))

import { uploadApi } from '@/api'

// Create a wrapper with QueryClientProvider
function createWrapper() {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
      mutations: { retry: false },
    },
  })
  return ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
  )
}

describe('useFileUpload', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  describe('initial state', () => {
    it('starts in idle state', () => {
      const { result } = renderHook(() => useFileUpload(), { wrapper: createWrapper() })

      expect(result.current.status).toBe('idle')
      expect(result.current.progress).toBeNull()
      expect(result.current.error).toBeNull()
      expect(result.current.selectedFile).toBeNull()
      expect(result.current.uploadedDocument).toBeNull()
      expect(result.current.isUploading).toBe(false)
      expect(result.current.isValidFile).toBe(false)
    })
  })

  describe('selectFile', () => {
    it('accepts valid PDF file', () => {
      const { result } = renderHook(() => useFileUpload(), { wrapper: createWrapper() })

      const file = new File(['content'], 'test.pdf', { type: 'application/pdf' })

      act(() => {
        const error = result.current.selectFile(file)
        expect(error).toBeNull()
      })

      expect(result.current.selectedFile).toBe(file)
      expect(result.current.isValidFile).toBe(true)
      expect(result.current.error).toBeNull()
    })

    it('accepts valid image file', () => {
      const { result } = renderHook(() => useFileUpload(), { wrapper: createWrapper() })

      const file = new File(['content'], 'image.png', { type: 'image/png' })

      act(() => {
        result.current.selectFile(file)
      })

      expect(result.current.selectedFile).toBe(file)
      expect(result.current.isValidFile).toBe(true)
    })

    it('accepts valid Word document', () => {
      const { result } = renderHook(() => useFileUpload(), { wrapper: createWrapper() })

      const file = new File(['content'], 'doc.docx', {
        type: 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
      })

      act(() => {
        result.current.selectFile(file)
      })

      expect(result.current.selectedFile).toBe(file)
      expect(result.current.isValidFile).toBe(true)
    })

    it('rejects invalid file type', () => {
      const { result } = renderHook(() => useFileUpload(), { wrapper: createWrapper() })

      const file = new File(['content'], 'test.exe', { type: 'application/x-executable' })

      act(() => {
        const error = result.current.selectFile(file)
        expect(error).not.toBeNull()
        expect(error?.type).toBe('invalid_type')
      })

      expect(result.current.selectedFile).toBeNull()
      expect(result.current.isValidFile).toBe(false)
      expect(result.current.error).not.toBeNull()
    })

    it('rejects file exceeding 5GB', () => {
      const { result } = renderHook(() => useFileUpload(), { wrapper: createWrapper() })

      // Create a mock file with size > 5GB
      const file = new File(['content'], 'huge.pdf', { type: 'application/pdf' })
      Object.defineProperty(file, 'size', { value: 6 * 1024 * 1024 * 1024 })

      act(() => {
        const error = result.current.selectFile(file)
        expect(error).not.toBeNull()
        expect(error?.type).toBe('file_too_large')
      })

      expect(result.current.selectedFile).toBeNull()
      expect(result.current.isValidFile).toBe(false)
    })

    it('rejects empty file', () => {
      const { result } = renderHook(() => useFileUpload(), { wrapper: createWrapper() })

      const file = new File([], 'empty.pdf', { type: 'application/pdf' })

      act(() => {
        const error = result.current.selectFile(file)
        expect(error).not.toBeNull()
        expect(error?.type).toBe('file_too_large')
        expect(error?.message).toContain('empty')
      })

      expect(result.current.selectedFile).toBeNull()
    })

    it('clears selection when passed null', () => {
      const { result } = renderHook(() => useFileUpload(), { wrapper: createWrapper() })

      const file = new File(['content'], 'test.pdf', { type: 'application/pdf' })

      act(() => {
        result.current.selectFile(file)
      })

      expect(result.current.selectedFile).toBe(file)

      act(() => {
        result.current.selectFile(null)
      })

      expect(result.current.selectedFile).toBeNull()
      expect(result.current.status).toBe('idle')
    })

    it('clears previous error when selecting new file', () => {
      const { result } = renderHook(() => useFileUpload(), { wrapper: createWrapper() })

      // First select invalid file
      const invalidFile = new File(['content'], 'test.exe', { type: 'application/x-executable' })
      act(() => {
        result.current.selectFile(invalidFile)
      })
      expect(result.current.error).not.toBeNull()

      // Then select valid file
      const validFile = new File(['content'], 'test.pdf', { type: 'application/pdf' })
      act(() => {
        result.current.selectFile(validFile)
      })
      expect(result.current.error).toBeNull()
    })
  })

  describe('startUpload', () => {
    it('uploads file successfully', async () => {
      const mockDocument = { id: 1, title: 'test.pdf', status: 'pending' }
      vi.mocked(uploadApi.uploadFile).mockResolvedValueOnce(mockDocument as never)

      const onSuccess = vi.fn()
      const { result } = renderHook(
        () => useFileUpload({ onSuccess }),
        { wrapper: createWrapper() }
      )

      const file = new File(['content'], 'test.pdf', { type: 'application/pdf' })

      act(() => {
        result.current.selectFile(file)
      })

      await act(async () => {
        await result.current.startUpload()
      })

      await waitFor(() => {
        expect(result.current.status).toBe('success')
      })

      expect(result.current.uploadedDocument).toEqual(mockDocument)
      expect(onSuccess).toHaveBeenCalledWith(mockDocument)
    })

    it('handles upload error', async () => {
      const error = new Error('Upload failed')
      vi.mocked(uploadApi.uploadFile).mockRejectedValueOnce(error)

      const onError = vi.fn()
      const { result } = renderHook(
        () => useFileUpload({ onError }),
        { wrapper: createWrapper() }
      )

      const file = new File(['content'], 'test.pdf', { type: 'application/pdf' })

      act(() => {
        result.current.selectFile(file)
      })

      await act(async () => {
        await result.current.startUpload()
      })

      await waitFor(() => {
        expect(result.current.status).toBe('error')
      })

      expect(result.current.error).toBeTruthy()
      expect(onError).toHaveBeenCalled()
    })

    it('sets error when no file selected', async () => {
      const { result } = renderHook(() => useFileUpload(), { wrapper: createWrapper() })

      await act(async () => {
        await result.current.startUpload()
      })

      expect(result.current.error).not.toBeNull()
      expect((result.current.error as { type: string })?.type).toBe('no_file')
    })

    it('sets isUploading during upload', async () => {
      let resolveUpload!: (value: unknown) => void
      vi.mocked(uploadApi.uploadFile).mockImplementationOnce(
        () => new Promise((resolve) => { resolveUpload = resolve as typeof resolveUpload })
      )

      const { result } = renderHook(() => useFileUpload(), { wrapper: createWrapper() })

      const file = new File(['content'], 'test.pdf', { type: 'application/pdf' })

      act(() => {
        result.current.selectFile(file)
      })

      // Start upload but don't await
      act(() => {
        result.current.startUpload()
      })

      await waitFor(() => {
        expect(result.current.isUploading).toBe(true)
      })

      // Resolve the upload
      await act(async () => {
        resolveUpload!({ id: 1, title: 'test.pdf', status: 'pending' })
      })

      await waitFor(() => {
        expect(result.current.isUploading).toBe(false)
      })
    })
  })

  describe('reset', () => {
    it('resets all state', async () => {
      const mockDocument = { id: 1, title: 'test.pdf', status: 'pending' }
      vi.mocked(uploadApi.uploadFile).mockResolvedValueOnce(mockDocument as never)

      const { result } = renderHook(() => useFileUpload(), { wrapper: createWrapper() })

      const file = new File(['content'], 'test.pdf', { type: 'application/pdf' })

      act(() => {
        result.current.selectFile(file)
      })

      await act(async () => {
        await result.current.startUpload()
      })

      await waitFor(() => {
        expect(result.current.status).toBe('success')
      })

      act(() => {
        result.current.reset()
      })

      expect(result.current.status).toBe('idle')
      expect(result.current.selectedFile).toBeNull()
      expect(result.current.uploadedDocument).toBeNull()
      expect(result.current.progress).toBeNull()
      expect(result.current.error).toBeNull()
    })
  })
})

describe('formatFileSize', () => {
  it('formats 0 bytes', () => {
    expect(formatFileSize(0)).toBe('0 Bytes')
  })

  it('formats bytes', () => {
    expect(formatFileSize(500)).toBe('500 Bytes')
  })

  it('formats KB', () => {
    expect(formatFileSize(1024)).toBe('1 KB')
    expect(formatFileSize(1536)).toBe('1.5 KB')
  })

  it('formats MB', () => {
    expect(formatFileSize(1024 * 1024)).toBe('1 MB')
    expect(formatFileSize(1.5 * 1024 * 1024)).toBe('1.5 MB')
  })

  it('formats GB', () => {
    expect(formatFileSize(1024 * 1024 * 1024)).toBe('1 GB')
    expect(formatFileSize(2.5 * 1024 * 1024 * 1024)).toBe('2.5 GB')
  })
})

describe('getFileExtension', () => {
  it('returns extension for simple filename', () => {
    expect(getFileExtension('test.pdf')).toBe('pdf')
  })

  it('returns last extension for multiple dots', () => {
    expect(getFileExtension('file.backup.txt')).toBe('txt')
  })

  it('returns empty string for no extension', () => {
    expect(getFileExtension('filename')).toBe('')
  })

  it('returns lowercase extension', () => {
    expect(getFileExtension('TEST.PDF')).toBe('pdf')
  })
})

describe('getFileTypeName', () => {
  it('returns PDF for application/pdf', () => {
    expect(getFileTypeName('application/pdf')).toBe('PDF')
  })

  it('returns Word Document for docx', () => {
    expect(getFileTypeName('application/vnd.openxmlformats-officedocument.wordprocessingml.document')).toBe('Word Document')
  })

  it('returns Excel Spreadsheet for xlsx', () => {
    expect(getFileTypeName('application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')).toBe('Excel Spreadsheet')
  })

  it('returns PowerPoint for pptx', () => {
    expect(getFileTypeName('application/vnd.openxmlformats-officedocument.presentationml.presentation')).toBe('PowerPoint')
  })

  it('returns JPEG Image for image/jpeg', () => {
    expect(getFileTypeName('image/jpeg')).toBe('JPEG Image')
  })

  it('returns MP3 Audio for audio/mpeg', () => {
    expect(getFileTypeName('audio/mpeg')).toBe('MP3 Audio')
  })

  it('returns File for unknown type', () => {
    expect(getFileTypeName('application/unknown')).toBe('File')
  })
})
