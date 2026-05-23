// frontend/components/ui/MarkdownRenderer.tsx

'use client'

import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import rehypeHighlight from 'rehype-highlight'

import 'highlight.js/styles/github-dark.css'

export function MarkdownRenderer({
  content,
}: {
  content: string
}) {
  return (
    <div
      className="
        prose prose-sm max-w-none
        prose-headings:text-nexus-dark
        prose-p:text-nexus-body
        prose-strong:text-nexus-dark
        prose-code:text-[#C7254E]
        prose-pre:bg-[#111827]
        prose-pre:text-white
        prose-pre:overflow-x-auto
        prose-pre:rounded-lg
        prose-pre:border
        prose-pre:border-white/10
        prose-pre:p-4
        prose-code:before:hidden
        prose-code:after:hidden
      "
    >
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        rehypePlugins={[rehypeHighlight]}
      >
        {content}
      </ReactMarkdown>
    </div>
  )
}