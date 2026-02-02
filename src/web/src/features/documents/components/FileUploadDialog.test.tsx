import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import type { ReactNode } from 'react'
import { FileUploadDialog } from './FileUploadDialog'

// Mock the hooks
vi.mock('@/hooks', () => ({
  useFileUpload: vi.fn(),
  formatFileSize: vi.fn((bytes: number) => `${bytes} bytes`),
  getFileTypeName: vi.fn((type: string) => type || 'File'),
}))

import { useFileUpload } from '@/hooks'

// Create wrapper with QueryClient
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

function renderWithProviders(ui: React.ReactElement) {
  return render(ui, { wrapper: createWrapper() })
}

describe('FileUploadDialog', () => {
  const defaultMockHook = {
    status: 'idle' as const,
    progress: null,
    error: null,
    selectedFile: null,
    uploadedDocument: null,
    selectFile: vi.fn(),
    startUpload: vi.fn(),
    cancelUpload: vi.fn(),
    reset: vi.fn(),
    isUploading: false,
    isValidFile: false,
  }

  beforeEach(() => {
    vi.clearAllMocks()
    vi.mocked(useFileUpload).mockReturnValue(defaultMockHook)
  })

  describe('rendering', () => {
    it('renders dialog when open', () => {
      renderWithProviders(
        <FileUploadDialog open={true} onOpenChange={vi.fn()} />
      )

      expect(screen.getByText('Upload Document')).toBeInTheDocument()
      expect(screen.getByText(/Upload a file to add it/)).toBeInTheDocument()
    })

    it('does not render when closed', () => {
      renderWithProviders(
        <FileUploadDialog open={false} onOpenChange={vi.fn()} />
      )

      expect(screen.queryByText('Upload Document')).not.toBeInTheDocument()
    })

    it('renders drop zone with instructions', () => {
      renderWithProviders(
        <FileUploadDialog open={true} onOpenChange={vi.fn()} />
      )

      expect(screen.getByText('Drag and drop your file here')).toBeInTheDocument()
      expect(screen.getByText('or click to browse')).toBeInTheDocument()
      expect(screen.getByRole('button', { name: 'Browse files' })).toBeInTheDocument()
    })

    it('renders Cancel and Upload buttons', () => {
      renderWithProviders(
        <FileUploadDialog open={true} onOpenChange={vi.fn()} />
      )

      expect(screen.getByRole('button', { name: 'Cancel' })).toBeInTheDocument()
      expect(screen.getByRole('button', { name: 'Upload' })).toBeInTheDocument()
    })

    it('renders accessible drop zone region', () => {
      renderWithProviders(
        <FileUploadDialog open={true} onOpenChange={vi.fn()} />
      )

      expect(screen.getByRole('region', { name: 'File drop zone' })).toBeInTheDocument()
    })
  })

  describe('file selection', () => {
    it('shows selected file info', () => {
      const mockFile = new File(['content'], 'test.pdf', { type: 'application/pdf' })
      vi.mocked(useFileUpload).mockReturnValue({
        ...defaultMockHook,
        selectedFile: mockFile,
        isValidFile: true,
      })

      renderWithProviders(
        <FileUploadDialog open={true} onOpenChange={vi.fn()} />
      )

      expect(screen.getByText('test.pdf')).toBeInTheDocument()
    })

    it('calls selectFile when file input changes', async () => {
      const user = userEvent.setup()
      const selectFile = vi.fn()
      vi.mocked(useFileUpload).mockReturnValue({
        ...defaultMockHook,
        selectFile,
      })

      renderWithProviders(
        <FileUploadDialog open={true} onOpenChange={vi.fn()} />
      )

      const file = new File(['content'], 'test.pdf', { type: 'application/pdf' })
      const input = screen.getByLabelText('File upload input')

      await user.upload(input, file)

      expect(selectFile).toHaveBeenCalledWith(file)
    })

    it('shows clear button when file is selected and clears on click', async () => {
      const user = userEvent.setup()
      const selectFile = vi.fn()
      const mockFile = new File(['content'], 'test.pdf', { type: 'application/pdf' })
      vi.mocked(useFileUpload).mockReturnValue({
        ...defaultMockHook,
        selectedFile: mockFile,
        isValidFile: true,
        selectFile,
      })

      renderWithProviders(
        <FileUploadDialog open={true} onOpenChange={vi.fn()} />
      )

      const clearButton = screen.getByRole('button', { name: 'Clear selected file' })
      expect(clearButton).toBeInTheDocument()

      await user.click(clearButton)
      expect(selectFile).toHaveBeenCalledWith(null)
    })
  })

  describe('drag and drop', () => {
    it('handles file drop', () => {
      const selectFile = vi.fn()
      vi.mocked(useFileUpload).mockReturnValue({
        ...defaultMockHook,
        selectFile,
      })

      renderWithProviders(
        <FileUploadDialog open={true} onOpenChange={vi.fn()} />
      )

      const dropZone = screen.getByRole('region', { name: 'File drop zone' })

      const file = new File(['content'], 'test.pdf', { type: 'application/pdf' })
      const dataTransfer = {
        files: [file],
        items: [{ kind: 'file', type: file.type, getAsFile: () => file }],
        types: ['Files'],
      }

      fireEvent.drop(dropZone, { dataTransfer })

      expect(selectFile).toHaveBeenCalledWith(file)
    })

    it('does not throw on drag over', () => {
      renderWithProviders(
        <FileUploadDialog open={true} onOpenChange={vi.fn()} />
      )

      const dropZone = screen.getByRole('region', { name: 'File drop zone' })

      // Verify drag events are handled without error
      expect(() => {
        fireEvent.dragOver(dropZone)
      }).not.toThrow()
    })

    it('does not throw on drag leave', () => {
      renderWithProviders(
        <FileUploadDialog open={true} onOpenChange={vi.fn()} />
      )

      const dropZone = screen.getByRole('region', { name: 'File drop zone' })

      // Verify drag events are handled without error
      expect(() => {
        fireEvent.dragOver(dropZone)
        fireEvent.dragLeave(dropZone)
      }).not.toThrow()
    })
  })

  describe('upload flow', () => {
    it('starts upload when Upload button clicked', async () => {
      const user = userEvent.setup()
      const startUpload = vi.fn()
      const mockFile = new File(['content'], 'test.pdf', { type: 'application/pdf' })
      vi.mocked(useFileUpload).mockReturnValue({
        ...defaultMockHook,
        selectedFile: mockFile,
        isValidFile: true,
        startUpload,
      })

      renderWithProviders(
        <FileUploadDialog open={true} onOpenChange={vi.fn()} />
      )

      const uploadButton = screen.getByRole('button', { name: 'Upload' })
      await user.click(uploadButton)

      expect(startUpload).toHaveBeenCalled()
    })

    it('disables Upload button when no valid file', () => {
      vi.mocked(useFileUpload).mockReturnValue({
        ...defaultMockHook,
        isValidFile: false,
      })

      renderWithProviders(
        <FileUploadDialog open={true} onOpenChange={vi.fn()} />
      )

      const uploadButton = screen.getByRole('button', { name: 'Upload' })
      expect(uploadButton).toBeDisabled()
    })

    it('disables buttons during upload', () => {
      vi.mocked(useFileUpload).mockReturnValue({
        ...defaultMockHook,
        isUploading: true,
        progress: { loaded: 500, total: 1000, percent: 50 },
      })

      renderWithProviders(
        <FileUploadDialog open={true} onOpenChange={vi.fn()} />
      )

      expect(screen.getByRole('button', { name: 'Cancel' })).toBeDisabled()
      expect(screen.getByRole('button', { name: 'Uploading...' })).toBeDisabled()
    })

    it('shows progress bar during upload', () => {
      vi.mocked(useFileUpload).mockReturnValue({
        ...defaultMockHook,
        status: 'uploading',
        isUploading: true,
        progress: { loaded: 500, total: 1000, percent: 50 },
      })

      renderWithProviders(
        <FileUploadDialog open={true} onOpenChange={vi.fn()} />
      )

      expect(screen.getByText('Uploading... 50%')).toBeInTheDocument()
      expect(screen.getByText('500 bytes / 1000 bytes')).toBeInTheDocument()
    })

    it('shows finalizing message when completing', () => {
      vi.mocked(useFileUpload).mockReturnValue({
        ...defaultMockHook,
        status: 'completing',
        isUploading: true,
        progress: { loaded: 1000, total: 1000, percent: 100 },
      })

      renderWithProviders(
        <FileUploadDialog open={true} onOpenChange={vi.fn()} />
      )

      expect(screen.getByText('Finalizing...')).toBeInTheDocument()
    })
  })

  describe('success state', () => {
    it('shows success message on completion', () => {
      const mockDocument = { id: 1, title: 'test.pdf', status: 'pending' }
      vi.mocked(useFileUpload).mockReturnValue({
        ...defaultMockHook,
        status: 'success',
        uploadedDocument: mockDocument as never,
      })

      renderWithProviders(
        <FileUploadDialog open={true} onOpenChange={vi.fn()} />
      )

      expect(screen.getByText('Upload complete!')).toBeInTheDocument()
      expect(screen.getByText('test.pdf')).toBeInTheDocument()
    })

    it('shows upload another button on success and calls reset when clicked', async () => {
      const user = userEvent.setup()
      const reset = vi.fn()
      const mockDocument = { id: 1, title: 'test.pdf', status: 'pending' }
      vi.mocked(useFileUpload).mockReturnValue({
        ...defaultMockHook,
        status: 'success',
        uploadedDocument: mockDocument as never,
        reset,
      })

      renderWithProviders(
        <FileUploadDialog open={true} onOpenChange={vi.fn()} />
      )

      const uploadAnotherButton = screen.getByRole('button', { name: 'Upload another file' })
      await user.click(uploadAnotherButton)

      expect(reset).toHaveBeenCalled()
    })

    it('calls onUploadComplete callback', async () => {
      const onUploadComplete = vi.fn()
      const mockDocument = { id: 1, title: 'test.pdf', status: 'pending' }

      // Mock useFileUpload to call the onSuccess callback
      vi.mocked(useFileUpload).mockImplementation((options) => {
        // Simulate calling onSuccess immediately for test
        if (options?.onSuccess) {
          setTimeout(() => options.onSuccess?.(mockDocument as never), 0)
        }
        return {
          ...defaultMockHook,
          status: 'success',
          uploadedDocument: mockDocument as never,
        }
      })

      renderWithProviders(
        <FileUploadDialog
          open={true}
          onOpenChange={vi.fn()}
          onUploadComplete={onUploadComplete}
        />
      )

      await waitFor(() => {
        expect(onUploadComplete).toHaveBeenCalledWith(mockDocument)
      })
    })

    it('shows Done button on success', () => {
      const onOpenChange = vi.fn()
      const mockDocument = { id: 1, title: 'test.pdf', status: 'pending' }
      vi.mocked(useFileUpload).mockReturnValue({
        ...defaultMockHook,
        status: 'success',
        uploadedDocument: mockDocument as never,
      })

      renderWithProviders(
        <FileUploadDialog open={true} onOpenChange={onOpenChange} />
      )

      expect(screen.getByRole('button', { name: 'Done' })).toBeInTheDocument()
    })
  })

  describe('error state', () => {
    it('shows error message on failure', () => {
      vi.mocked(useFileUpload).mockReturnValue({
        ...defaultMockHook,
        status: 'error',
        error: new Error('Network error'),
      })

      renderWithProviders(
        <FileUploadDialog open={true} onOpenChange={vi.fn()} />
      )

      expect(screen.getByText('Upload failed')).toBeInTheDocument()
      expect(screen.getByText('Network error')).toBeInTheDocument()
    })

    it('shows validation error message', () => {
      vi.mocked(useFileUpload).mockReturnValue({
        ...defaultMockHook,
        error: { type: 'invalid_type', message: 'File type not supported' },
      })

      renderWithProviders(
        <FileUploadDialog open={true} onOpenChange={vi.fn()} />
      )

      expect(screen.getByText('Upload failed')).toBeInTheDocument()
      expect(screen.getByText('File type not supported')).toBeInTheDocument()
    })
  })

  describe('dialog close behavior', () => {
    it('calls reset and onOpenChange when closing', async () => {
      const user = userEvent.setup()
      const reset = vi.fn()
      const onOpenChange = vi.fn()
      vi.mocked(useFileUpload).mockReturnValue({
        ...defaultMockHook,
        reset,
      })

      renderWithProviders(
        <FileUploadDialog open={true} onOpenChange={onOpenChange} />
      )

      const cancelButton = screen.getByRole('button', { name: 'Cancel' })
      await user.click(cancelButton)

      expect(reset).toHaveBeenCalled()
      expect(onOpenChange).toHaveBeenCalledWith(false)
    })

    it('prevents closing during upload', () => {
      const reset = vi.fn()
      const onOpenChange = vi.fn()
      vi.mocked(useFileUpload).mockReturnValue({
        ...defaultMockHook,
        isUploading: true,
        reset,
      })

      renderWithProviders(
        <FileUploadDialog open={true} onOpenChange={onOpenChange} />
      )

      // The cancel button should be disabled during upload
      const cancelButton = screen.getByRole('button', { name: 'Cancel' })
      expect(cancelButton).toBeDisabled()
    })
  })
})
