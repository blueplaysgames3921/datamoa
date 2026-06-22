/**
 * File upload via IPC — handles sending files from renderer to Python backend
 * Files are read in the renderer, sent as base64 through IPC, written to temp, then submitted
 */

export async function uploadFile(file: File): Promise<{ record_id: string; status: string }> {
  // Read file as ArrayBuffer
  const buffer = await file.arrayBuffer()
  const uint8 = new Uint8Array(buffer)

  // Convert to base64
  let binary = ''
  for (let i = 0; i < uint8.byteLength; i++) {
    binary += String.fromCharCode(uint8[i])
  }
  const base64 = btoa(binary)

  // Send through IPC
  return window.datamoa.pipeline.submitFile({
    filename: file.name,
    mime_type: file.type,
    size: file.size,
    data_b64: base64,
  })
}

export async function uploadFiles(
  files: File[],
  onProgress?: (done: number, total: number, filename: string) => void
): Promise<Array<{ record_id: string; status: string; filename: string }>> {
  const results: Array<{ record_id: string; status: string; filename: string }> = []
  
  for (let i = 0; i < files.length; i++) {
    const file = files[i]
    onProgress?.(i, files.length, file.name)
    try {
      const result = await uploadFile(file)
      results.push({ ...result, filename: file.name })
    } catch (e) {
      results.push({ record_id: '', status: 'error', filename: file.name })
    }
  }
  
  onProgress?.(files.length, files.length, '')
  return results
}
