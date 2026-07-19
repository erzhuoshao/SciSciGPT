'use client'

import * as React from 'react'
import Textarea from 'react-textarea-autosize'
import { default as NextImage } from 'next/image'
import { motion, AnimatePresence } from 'framer-motion'

import { useActions, useUIState, useAIState } from 'ai/rsc'
import { type AI } from '@/lib/chat/actions'
import { Button } from '@/components/ui/button'
import { IconArrowElbow, IconPlus, IconUpload, IconX } from '@/components/ui/icons'
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger
} from '@/components/ui/tooltip'
import { useEnterSubmit } from '@/lib/hooks/use-enter-submit'
import { usePathname } from 'next/navigation'
import { ModelSelector } from '@/components/model_selector'
import { FooterText } from '@/components/footer'
import { toast } from 'sonner'

import { useState, useRef, useCallback, useEffect } from 'react';

const DEFAULT_MODEL_ID = 'claude-4.6'
const ALLOWED_MODEL_IDS = new Set(['claude-3.7', 'claude-4.0', 'claude-4.5', 'claude-4.6'])


export function PromptForm({
  input,
  setInput,
  session
}: {
  input: string
  setInput: (value: string) => void
  session?: any
}) {
  const pathname = usePathname()
  const { formRef, onKeyDown } = useEnterSubmit()
  const inputRef = React.useRef<HTMLTextAreaElement>(null)
  const { submitUserMessage } = useActions()
  const [_, setMessages] = useUIState<typeof AI>()
  const [aiState] = useAIState<typeof AI>()
  const [userApiKey, setUserApiKey] = useState<string | null>(null)

  const handleModelChange = (modelId: string) => {
    setSelectedModelId(modelId)
    if (typeof window !== 'undefined') {
      localStorage.setItem('selectedModelId', modelId)
    }
  }
  const [selectedModelId, setSelectedModelId] = useState<string>(() => {
    if (typeof window !== 'undefined') {
      const storedModelId = localStorage.getItem('selectedModelId')
      if (storedModelId && ALLOWED_MODEL_IDS.has(storedModelId)) {
        return storedModelId
      }
      if (storedModelId && !ALLOWED_MODEL_IDS.has(storedModelId)) {
        localStorage.removeItem('selectedModelId')
      }
    }
    return DEFAULT_MODEL_ID
  })

  React.useEffect(() => {
    if (inputRef.current) {
      inputRef.current.focus()
    }
  }, [])

  const [previewOpen, setPreviewOpen] = useState(false);
  const [previewImage, setPreviewImage] = useState('');
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [quotaExceeded, setQuotaExceeded] = useState(false);
  const [quotaMessage, setQuotaMessage] = useState<string | null>(null);

  useEffect(() => {
    const loadApiKey = async () => {
      if (!session?.user?.id) return
      try {
        const resp = await fetch('/api/settings/api-key', { method: 'GET' })
        if (!resp.ok) return
        const data = await resp.json()
        if (data?.apiKey) {
          setUserApiKey(data.apiKey)
          setQuotaExceeded(false)
          setQuotaMessage(null)
        }
      } catch (err) {
        // ignore fetch errors; fall back to server-side retrieval
      }
    }
    loadApiKey()
  }, [session?.user?.id])

  const uploadButton = (
    <button style={{ border: 0, background: 'none' }} type="button">
      <IconUpload />
    </button>
  );

  const [uploadedImages, setUploadedImages] = useState<string[]>([]);

  const convertToPng = (dataUrl: string): Promise<string> => {
    return new Promise((resolve, reject) => {
      const img = new Image();
      img.onload = () => {
        const canvas = document.createElement('canvas');
        canvas.width = img.width;
        canvas.height = img.height;
        const ctx = canvas.getContext('2d');
        if (!ctx) {
          reject(new Error('Failed to get canvas context'));
          return;
        }
        ctx.drawImage(img, 0, 0);
        resolve(canvas.toDataURL('image/png'));
      };
      img.onerror = reject;
      img.src = dataUrl;
    });
  };

  const handleImageUpload = async (event: React.ChangeEvent<HTMLInputElement>) => {
    const files = event.target.files;
    if (files && files.length > 0 && uploadedImages.length < 5) {
      const file = files[0];
      const reader = new FileReader();
      reader.onloadend = async () => {
        const pngDataUrl = await convertToPng(reader.result as string);
        setUploadedImages(prev => [...prev, pngDataUrl]);
      };
      reader.readAsDataURL(file);
    }
  };

  const handleDeleteImage = (index: number) => {
    setUploadedImages(prev => prev.filter((_, i) => i !== index));
  };

  const [hoveredIndex, setHoveredIndex] = useState<number | null>(null);

  const [imageDimensions, setImageDimensions] = useState<{ [key: number]: { width: number, height: number } }>({});

  const onImageLoad = useCallback((index: number, event: React.SyntheticEvent<HTMLImageElement>) => {
    const { naturalWidth, naturalHeight } = event.currentTarget;
    setImageDimensions(prev => ({
      ...prev,
      [index]: { width: naturalWidth, height: naturalHeight }
    }));
  }, []);

  return (
    <form
      ref={formRef}
      onSubmit={async (e: React.FormEvent) => {
        e.preventDefault()

        // Blur focus on mobile
        if (window.innerWidth < 600) {
          // @ts-ignore
          e.target['message'].blur()
        }

        if (isSubmitting || quotaExceeded) {
          return
        }

        const value = input.trim()
        if (!value) return

        setIsSubmitting(true)

        if (session?.user?.id) {
          try {
            const resp = await fetch('/api/quota', { 
              method: 'POST',
              headers: {
                'Content-Type': 'application/json'
              },
              body: JSON.stringify({ chatId: aiState.chatId })
            })
            if (!resp.ok) {
              throw new Error('Failed to check quota')
            }
            const data = await resp.json()
            if (!data.allowed && !userApiKey) {
              setQuotaExceeded(true)
              const message =
                data.limit !== undefined
                  ? `Daily limit reached (${data.limit} messages). Add your Anthropic API key in Settings for unlimited usage.`
                  : 'Daily limit reached. Add your Anthropic API key in Settings for unlimited usage.'
              setQuotaMessage(message)
              toast.error(
                <span>
                  {message}{' '}
                  <a href="/settings" className="underline font-semibold">
                    Settings
                  </a>
                </span>
              )
              setIsSubmitting(false)
              return
            }
          } catch (err) {
            if (!userApiKey) {
              toast.error(
                <span>
                  Could not verify quota. Please try again or check{' '}
                  <a href="/settings" className="underline font-semibold">
                    Settings
                  </a>
                  .
                </span>
              )
              setIsSubmitting(false)
              return
            }
          }
        }

        try {
          // Convert all images to PNG format
          const pngImageList = await Promise.all(uploadedImages.map(convertToPng));

          setInput('')

          const isNewChat = pathname === '/' || !pathname.startsWith('/chat/')
          
          const responseMessage = await submitUserMessage(
            value,
            pngImageList,
            selectedModelId,
            userApiKey ?? undefined
          )
          
          setMessages((currentMessages: any) => [...currentMessages, responseMessage])
          
          if (isNewChat && responseMessage) {
            const chatId = aiState.chatId
            if (chatId) {
              const newChat = {
                id: chatId,
                title: aiState.title || value.substring(0, 100),
                userId: session?.user?.id,
                createdAt: new Date(),
                messages: [],
                path: `/chat/${chatId}`,
                status: 'active' as const
              }
              
              window.dispatchEvent(new CustomEvent('newChatAdded', {
                detail: newChat
              }))
            }
          }

          // Clear uploaded images after submission
          setUploadedImages([]);
        } catch (err) {
          toast.error('Failed to send message. Please try again.')
        } finally {
          setIsSubmitting(false)
        }
      }}
    >
      {uploadedImages.length > 0 && (
        <div className="flex flex-wrap gap-2 mb-2">
          {uploadedImages.map((image, index) => (
            <div 
              key={index} 
              className="relative size-[50px]"
              onMouseEnter={() => setHoveredIndex(index)}
              onMouseLeave={() => setHoveredIndex(null)}
            >
              <div className="size-full overflow-hidden rounded border border-gray-300 shadow-sm">
                <NextImage 
                  src={image} 
                  alt={`Uploaded image ${index + 1}`} 
                  width={50}
                  height={50}
                  onLoad={(event) => onImageLoad(index, event)}
                  className="object-cover size-full transition-transform duration-200 hover:scale-105"
                />
              </div>
              <AnimatePresence>
                {hoveredIndex === index && (
                  <motion.button
                    initial={{ opacity: 0, scale: 0.8 }}
                    animate={{ opacity: 1, scale: 1 }}
                    exit={{ opacity: 0, scale: 0.8 }}
                    transition={{ duration: 0.2 }}
                    type="button"
                    onClick={() => handleDeleteImage(index)}
                    className="absolute -top-2 -right-2 bg-black text-white rounded-full p-1 hover:bg-gray-800 focus:outline-none focus:ring-2 focus:ring-gray-400/50"
                  >
                    <IconX className="size-3" />
                    <span className="sr-only">Delete image</span>
                  </motion.button>
                )}
              </AnimatePresence>
            </div>
          ))}
        </div>
      )}
      <div className="relative flex max-h-60 w-full grow overflow-hidden bg-background px-8 sm:rounded-md sm:border sm:px-12">
        <div className="absolute left-0 top-1/2 -translate-y-1/2 sm:left-4">
          <Tooltip>
            <TooltipTrigger asChild>
              <Button
                type="button"
                size="icon"
                variant="ghost"
                onClick={() => document.getElementById('image-upload')?.click()}
                disabled={uploadedImages.length >= 5}
                className="text-foreground"
              >
                <IconUpload />
                <span className="sr-only">Upload image</span>
              </Button>
            </TooltipTrigger>
            <TooltipContent>Upload image</TooltipContent>
          </Tooltip>
          <input
            id="image-upload"
            type="file"
            accept="image/*"
            onChange={handleImageUpload}
            className="hidden"
          />
        </div>
        <Textarea
          ref={inputRef}
          tabIndex={0}
          onKeyDown={onKeyDown}
          placeholder="Send a message."
          className="min-h-[60px] w-full resize-none bg-transparent px-4 py-[1.3rem] focus-within:outline-none sm:text-sm"
          autoFocus
          spellCheck={false}
          autoComplete="off"
          autoCorrect="off"
          name="message"
          rows={1}
          value={input}
          onChange={e => setInput(e.target.value)}
        />
        <div className="absolute right-0 top-1/2 -translate-y-1/2 sm:right-4">
          <Tooltip>
            <TooltipTrigger asChild>
              <Button
                type="submit"
                size="icon"
                disabled={input === '' || isSubmitting || quotaExceeded}
                title={quotaExceeded ? quotaMessage ?? 'Daily limit reached' : undefined}
              >
                <IconArrowElbow />
                <span className="sr-only">Send message</span>
              </Button>
            </TooltipTrigger>
            <TooltipContent>Send message</TooltipContent>
          </Tooltip>
        </div>
      </div>
      <div className="flex justify-between items-center pt-2">
        <FooterText className="hidden sm:block" />
        <div className="ml-auto">
          {session?.user && (
            <ModelSelector 
              session={session}
              selectedModelId={selectedModelId}
              onModelChange={handleModelChange}
            />
          )}
        </div>
      </div>
    </form>
  )
}
