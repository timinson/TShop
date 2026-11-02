import { useEffect, useRef, useState } from 'react'
import './chat-preview.css'

export default function ChatPreview() {
  const [open, setOpen] = useState(false)
  const buttonRef = useRef(null)

  useEffect(() => {
    if (!open) return
    const onKeyDown = event => {
      if (event.key === 'Escape') {
        setOpen(false)
        buttonRef.current?.focus()
      }
    }
    document.addEventListener('keydown', onKeyDown)
    return () => document.removeEventListener('keydown', onKeyDown)
  }, [open])

  return <aside className="chat-preview" aria-label="Чат магазина">
    <section className={`chat-preview-window${open ? ' is-open' : ''}`} id="chat-preview-window" aria-labelledby="chat-preview-title" aria-hidden={!open} inert={!open}>
      <div className="chat-preview-header"><div><p>SHOP / ПОМОЩЬ</p><h2 id="chat-preview-title">Чат с магазином</h2></div><button type="button" className="chat-preview-close" aria-label="Закрыть чат" onClick={() => { setOpen(false); buttonRef.current?.focus() }}><svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" aria-hidden="true"><path d="M6 6l12 12M18 6 6 18" /></svg></button></div>
      <div className="chat-preview-body">
        <div className="chat-preview-placeholder" aria-hidden="true"><div className="chat-preview-bubble">Здравствуйте! Чем я могу помочь?</div><div className="chat-preview-bubble is-reply">Помогите выбрать товар</div><div className="chat-preview-bubble">Конечно, подберём подходящий вариант.</div><div className="chat-preview-input">Написать сообщение <span>→</span></div></div>
        <div className="chat-preview-notice" role="status"><span className="chat-preview-sparkle" aria-hidden="true">✦</span><strong>Тут будет чат с ИИ-агентом</strong><span>Скоро здесь можно будет задать вопрос о товарах.</span></div>
      </div>
    </section>
    <button ref={buttonRef} type="button" className="chat-preview-toggle" aria-label={open ? 'Закрыть чат' : 'Открыть чат'} aria-expanded={open} aria-controls={open ? 'chat-preview-window' : undefined} onClick={() => setOpen(value => !value)}><svg width="25" height="25" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="M21 11.5a8.5 8.5 0 0 1-8.5 8.5H5l1.3-3.2A8.5 8.5 0 1 1 21 11.5Z" /><path d="M8.5 11.5h.01m4 0h.01m4 0h.01" strokeWidth="2.5" /></svg></button>
  </aside>
}
