// Emplacement: frontend/lib/websocket.ts

import { WebSocketMessage } from './types'

export type WebSocketEventHandler = (message: WebSocketMessage) => void

export class WebSocketClient {
  private ws: WebSocket | null = null
  private url: string
  private reconnectAttempts = 0
  private maxReconnectAttempts = 5
  private reconnectInterval = 1000
  private eventHandlers: Map<string, WebSocketEventHandler[]> = new Map()
  private isConnecting = false
  private shouldConnect = true

  constructor(url: string = process.env.WS_URL || 'ws://localhost:8000/ws') {
    this.url = url
  }

  connect(token?: string): Promise<void> {
    return new Promise((resolve, reject) => {
      if (this.isConnecting || (this.ws && this.ws.readyState === WebSocket.OPEN)) {
        resolve()
        return
      }

      this.isConnecting = true
      const wsUrl = token ? `${this.url}?token=${token}` : this.url

      try {
        this.ws = new WebSocket(wsUrl)

        this.ws.onopen = (event) => {
          console.log('WebSocket connecté')
          this.isConnecting = false
          this.reconnectAttempts = 0
          this.triggerHandlers('connection', { 
            type: 'connection', 
            data: { status: 'connected' }, 
            timestamp: new Date().toISOString() 
          })
          resolve()
        }

        this.ws.onmessage = (event) => {
          try {
            const message: WebSocketMessage = JSON.parse(event.data)
            console.log('WebSocket message reçu:', message)
            
            // Trigger handlers pour le type spécifique
            this.triggerHandlers(message.type, message)
            // Trigger handlers globaux
            this.triggerHandlers('*', message)
          } catch (error) {
            console.error('Erreur parsing message WebSocket:', error)
          }
        }

        this.ws.onclose = (event) => {
          console.log('WebSocket fermé:', event.code, event.reason)
          this.isConnecting = false
          this.ws = null
          
          this.triggerHandlers('connection', { 
            type: 'connection', 
            data: { status: 'disconnected', code: event.code }, 
            timestamp: new Date().toISOString() 
          })

          // Tentative de reconnexion automatique
          if (this.shouldConnect && this.reconnectAttempts < this.maxReconnectAttempts) {
            this.reconnectAttempts++
            console.log(`Tentative de reconnexion ${this.reconnectAttempts}/${this.maxReconnectAttempts}`)
            setTimeout(() => {
              if (this.shouldConnect) {
                this.connect(token).catch(console.error)
              }
            }, this.reconnectInterval * this.reconnectAttempts)
          }
        }

        this.ws.onerror = (error) => {
          console.error('Erreur WebSocket:', error)
          this.isConnecting = false
          reject(error)
        }

      } catch (error) {
        this.isConnecting = false
        reject(error)
      }
    })
  }

  disconnect() {
    this.shouldConnect = false
    if (this.ws) {
      this.ws.close()
      this.ws = null
    }
  }

  send(message: any) {
    if (this.ws && this.ws.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify(message))
    } else {
      console.warn('WebSocket non connecté, impossible d\'envoyer:', message)
    }
  }

  // Système d'événements
  on(eventType: string, handler: WebSocketEventHandler) {
    if (!this.eventHandlers.has(eventType)) {
      this.eventHandlers.set(eventType, [])
    }
    this.eventHandlers.get(eventType)!.push(handler)
  }

  off(eventType: string, handler: WebSocketEventHandler) {
    const handlers = this.eventHandlers.get(eventType)
    if (handlers) {
      const index = handlers.indexOf(handler)
      if (index > -1) {
        handlers.splice(index, 1)
      }
    }
  }

  private triggerHandlers(eventType: string, message: WebSocketMessage) {
    const handlers = this.eventHandlers.get(eventType) || []
    handlers.forEach(handler => {
      try {
        handler(message)
      } catch (error) {
        console.error('Erreur dans handler WebSocket:', error)
      }
    })
  }

  getStatus(): 'connecting' | 'connected' | 'disconnected' {
    if (this.isConnecting) return 'connecting'
    if (this.ws && this.ws.readyState === WebSocket.OPEN) return 'connected'
    return 'disconnected'
  }
}

// Instance globale
export const wsClient = new WebSocketClient()