import axios, { type AxiosInstance, type AxiosRequestConfig, type AxiosError } from 'axios'
import { ref, computed, onScopeDispose } from 'vue'

const apiClient: AxiosInstance = axios.create({
  baseURL: '/api/v1',
  timeout: 120000,
  headers: {
    'Content-Type': 'application/json',
  },
})

// Response interceptor for error handling
apiClient.interceptors.response.use(
  (response) => response,
  (error: AxiosError) => {
    if (axios.isCancel(error)) return Promise.reject(error)
    const message =
      (error.response?.data as { detail?: string })?.detail ||
      error.message ||
      'An unexpected error occurred'
    console.error(`API Error: ${error.response?.status} - ${message}`)
    return Promise.reject(error)
  }
)

export function useApi() {
  const activeRequests = ref(0)
  const loading = computed(() => activeRequests.value > 0)
  const error = ref<string | null>(null)
  const errors = ref<string[]>([])

  let controller = new AbortController()

  function cancelAll() {
    controller.abort()
    controller = new AbortController()
    activeRequests.value = 0
  }

  onScopeDispose(() => {
    controller.abort()
  })

  async function get<T>(url: string, config?: AxiosRequestConfig): Promise<T> {
    activeRequests.value++
    try {
      const response = await apiClient.get<T>(url, { ...config, signal: controller.signal })
      return response.data
    } catch (err) {
      if (axios.isCancel(err)) throw err
      const axiosError = err as AxiosError
      const msg =
        (axiosError.response?.data as { detail?: string })?.detail ||
        axiosError.message
      error.value = msg
      errors.value.push(msg)
      throw err
    } finally {
      activeRequests.value--
    }
  }

  async function post<T>(url: string, data?: unknown, config?: AxiosRequestConfig): Promise<T> {
    activeRequests.value++
    try {
      const response = await apiClient.post<T>(url, data, { ...config, signal: controller.signal })
      return response.data
    } catch (err) {
      if (axios.isCancel(err)) throw err
      const axiosError = err as AxiosError
      const msg =
        (axiosError.response?.data as { detail?: string })?.detail ||
        axiosError.message
      error.value = msg
      errors.value.push(msg)
      throw err
    } finally {
      activeRequests.value--
    }
  }

  async function put<T>(url: string, data?: unknown, config?: AxiosRequestConfig): Promise<T> {
    activeRequests.value++
    try {
      const response = await apiClient.put<T>(url, data, { ...config, signal: controller.signal })
      return response.data
    } catch (err) {
      if (axios.isCancel(err)) throw err
      const axiosError = err as AxiosError
      const msg =
        (axiosError.response?.data as { detail?: string })?.detail ||
        axiosError.message
      error.value = msg
      errors.value.push(msg)
      throw err
    } finally {
      activeRequests.value--
    }
  }

  async function del<T>(url: string, config?: AxiosRequestConfig): Promise<T> {
    activeRequests.value++
    try {
      const response = await apiClient.delete<T>(url, { ...config, signal: controller.signal })
      return response.data
    } catch (err) {
      if (axios.isCancel(err)) throw err
      const axiosError = err as AxiosError
      const msg =
        (axiosError.response?.data as { detail?: string })?.detail ||
        axiosError.message
      error.value = msg
      errors.value.push(msg)
      throw err
    } finally {
      activeRequests.value--
    }
  }

  return {
    loading,
    error,
    errors,
    get,
    post,
    put,
    del,
    cancelAll,
  }
}

export { apiClient }
