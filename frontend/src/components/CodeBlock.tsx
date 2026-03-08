interface CodeBlockProps {
  title: string;
  language?: string;
  code: string;
}

export default function CodeBlock({ title, language, code }: CodeBlockProps) {
  return (
    <div className="code-wrap">
      <div className="code-head">
        <strong>{title}</strong>
        {language && <span>{language}</span>}
      </div>
      <pre>
        <code>{code}</code>
      </pre>
    </div>
  );
}
