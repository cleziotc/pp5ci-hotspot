import type { PropsWithChildren } from 'react'

type Props = PropsWithChildren<{ title?: string; className?: string }>

export default function Panel({ title, className = '', children }: Props) {
  return <section className={'panel ' + className}>{title ? <h2>{title}</h2> : null}{children}</section>
}
