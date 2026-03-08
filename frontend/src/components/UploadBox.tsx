import { ChangeEvent } from 'react';

interface UploadBoxProps {
  onFile: (base64: string) => void;
}

export default function UploadBox({ onFile }: UploadBoxProps) {
  const handleChange = async (event: ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    if (!file) {
      return;
    }

    const arrayBuffer = await file.arrayBuffer();
    const bytes = new Uint8Array(arrayBuffer);
    let binary = '';
    bytes.forEach((byte) => {
      binary += String.fromCharCode(byte);
    });
    onFile(btoa(binary));
  };

  return (
    <label className="upload-box">
      <span>Upload brochure PDF (optional)</span>
      <input type="file" accept="application/pdf" onChange={handleChange} />
    </label>
  );
}
