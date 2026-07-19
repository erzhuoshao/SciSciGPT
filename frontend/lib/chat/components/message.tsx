'use client'

import { IconTool, IconUser } from '@/components/ui/icons'
import { cn } from '@/lib/utils'
import { spinner } from '@/components/spinner'
import { Markdown } from '@/lib/chat/components/markdown'
import { StreamableValue } from 'ai/rsc'
import { useStreamableText } from '@/lib/hooks/use-streamable-text'
import React from 'react'
import { process_xml } from '@/lib/chat/components/xml'

import './index.css';

// Cache for parsed XML segments to avoid re-parsing
const xmlParseCache = new Map<string, Array<{tag: string, content: string}>>()

function parseXMLIntoSegments(text: string): Array<{tag: string, content: string}> {
	// Check cache first
	if (xmlParseCache.has(text)) {
		return xmlParseCache.get(text)!
	}
	
	const segments: Array<{tag: string, content: string}> = [];
	let currentIndex = 0;
	
	// Find all XML opening tags
	const tagRegex = /<(\w+)(?:\s[^>]*)?>/g;
	let match;
	
	while ((match = tagRegex.exec(text)) !== null) {
		const tagName = match[1];
		const tagStart = match.index;
		const tagEnd = match.index + match[0].length;
  
		// Add content before this tag
		if (tagStart > currentIndex) {
			segments.push({
				tag: 'text',
				content: text.slice(currentIndex, tagStart)
			});
		}
  
		// Find the next opening tag to determine content end
		const nextTagRegex = /<(\w+)(?:\s[^>]*)?>/g;
		nextTagRegex.lastIndex = tagEnd;
		const nextMatch = nextTagRegex.exec(text);
  
		let contentEnd = text.length;
		if (nextMatch) {
			contentEnd = nextMatch.index;
		}
  
		// Extract content between current tag and next tag (or end of text)
		const content = text.slice(tagEnd, contentEnd);
  
		segments.push({
			tag: tagName,
			content: content
		});
  
		currentIndex = contentEnd;
	}
	
	// Add remaining content after last tag
	if (currentIndex < text.length) {
		segments.push({
			tag: 'text',
			content: text.slice(currentIndex)
		});
	}
	
	// Filter out empty segments
	const nonEmptySegments = segments.filter(segment => segment.content !== '');
	
	let result: Array<{tag: string, content: string}>
	// Always return an array - if no XML tags found or only empty segments, return original text as single segment
	if (nonEmptySegments.length === 0) {
		result = [{
			tag: 'text',
			content: text
		}];
	} else {
		result = nonEmptySegments;
	}
	
	// Cache the result (limit cache size to prevent memory leaks)
	if (xmlParseCache.size > 100) {
		const firstKey = xmlParseCache.keys().next().value
		if (firstKey) {
			xmlParseCache.delete(firstKey)
		}
	}
	xmlParseCache.set(text, result)
	
	return result;
}

export function UserMessage({ children }: { children: React.ReactNode }) {
  return (
    <div className="group-data-[role=user]/message:bg-primary group-data-[role=user]/message:text-primary-foreground flex gap-4 group-data-[role=user]/message:px-3 w-full group-data-[role=user]/message:w-fit group-data-[role=user]/message:ml-auto group-data-[role=user]/message:max-w-2xl group-data-[role=user]/message:py-2 rounded-xl py-4">
      {children}
    </div>
  )
}

export function BotMessage({
  content,
  className,
  icon=null,
  name=null,
  icon_invisible=true,
  header,
}: {
  content: string | StreamableValue<string>
  className?: string
  icon?: React.ReactNode,
  name?: string | null
  icon_invisible?: boolean
  header: string
}) {
  // For streamable content, pass directly to Markdown for animation
  const rawText = useStreamableText(content).trim()

  const processedText = process_xml(rawText)

  if (processedText === '') { return null }

  const hasIcon = Boolean(icon)

  return (
    <div className={cn('group relative flex items-start md:-ml-12', className)}>
      {name && (
        <div className="flex shrink-0 select-none agent-name">
          {name}
        </div>
      )}
      <div
        className={cn(
          'flex size-[25px] shrink-0 select-none items-center justify-center border bg-background shadow-sm bot-icon',
          (!hasIcon || icon_invisible) && 'invisible')}
        aria-hidden={!hasIcon}
      >
        {icon}
      </div>
      <div className={cn("ml-4 flex-1 space-y-2 overflow-hidden px-1")}>
        <Markdown text={processedText} header={header}/>
      </div>
    </div>
  )
}

export function BotCard({
  children,
  icon, icon_invisible,
  name,
}: {
  children: React.ReactNode
  icon?: React.ReactNode,
  icon_invisible?: boolean
  name?: string
}) {
  return (
    <div className="group relative mb-4 flex items-start md:-ml-12">
      {name && (
        <div className="flex shrink-0 select-none agent-name">
          {name}
        </div>
      )}
      <div
        className={cn(
          'flex size-[25px] shrink-0 select-none items-center justify-center border bg-background shadow-sm bot-icon',
          icon_invisible && 'invisible')}
      >
        {icon}
      </div>
      <div className="flex-1 px-1 ml-4 space-y-2 overflow-hidden">{children}</div>
    </div>
  )
}


export function UserCard({
  children,
}: {
  children: React.ReactNode
}) {
  return (
    <div className='human-message'>
      <div className="group relative flex items-start md:-ml-12 human-chat">
        <div className="flex-1">{children}</div>
      </div>
    </div>
  )
}

export function SystemMessage({ children }: { children: React.ReactNode }) {
  return (
    <div
      className={
        'mt-2 flex items-center justify-center gap-2 text-sm text-foreground'
      }
    >
      <div className={'max-w-[600px] flex-initial p-2'}>{children}</div>
    </div>
  )
}

export function SpinnerMessage() {
  return (
    <div className="group relative flex items-start md:-ml-12">
      <div className="flex size-[24px] shrink-0 select-none items-center justify-center border bg-background shadow-sm bot-icon invisible" />
      <div className="ml-4 h-[24px] flex flex-row items-center flex-1 space-y-2 overflow-hidden px-1">
        {spinner}
      </div>
    </div>
  )
}
