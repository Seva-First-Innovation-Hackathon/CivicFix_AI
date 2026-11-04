import React, { useRef, useState } from 'react';
import { UploadCloud, X, Image as ImageIcon, AlertCircle } from 'lucide-react';

interface FileUploadProps {
  onFileSelect: (file: File | null) => void;
  selectedFile: File | null;
  label?: string;
  accept?: string;
  maxSizeMB?: number;
}

export const FileUpload: React.FC<FileUploadProps> = ({
  onFileSelect,
  selectedFile,
  label = 'Upload Photographic Evidence',
  accept = 'image/jpeg,image/png,image/webp,image/jpg',
  maxSizeMB = 10,
}) => {
  const [dragActive, setDragActive] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  const validateAndSetFile = (file: File) => {
    setError(null);

    // Size check
    if (file.size > maxSizeMB * 1024 * 1024) {
      setError(`File size exceeds maximum permitted ${maxSizeMB}MB.`);
      return;
    }

    // Type check
    const allowedTypes = accept.split(',');
    if (!allowedTypes.includes(file.type)) {
      setError('Invalid file format. Please upload JPG, PNG, or WebP images.');
      return;
    }

    onFileSelect(file);
    const reader = new FileReader();
    reader.onloadend = () => {
      setPreviewUrl(reader.result as string);
    };
    reader.readAsDataURL(file);
  };

  const handleDrag = (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    if (e.type === 'dragenter' || e.type === 'dragover') {
      setDragActive(true);
    } else if (e.type === 'dragleave') {
      setDragActive(false);
    }
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setDragActive(false);
    if (e.dataTransfer.files && e.dataTransfer.files[0]) {
      validateAndSetFile(e.dataTransfer.files[0]);
    }
  };

  const handleChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files[0]) {
      validateAndSetFile(e.target.files[0]);
    }
  };

  const handleRemove = () => {
    onFileSelect(null);
    setPreviewUrl(null);
    setError(null);
    if (inputRef.current) {
      inputRef.current.value = '';
    }
  };

  return (
    <div className="space-y-2">
      <label className="block text-sm font-medium text-slate-700">{label}</label>

      {error && (
        <div className="flex items-center gap-2 p-2.5 bg-rose-50 border border-rose-200 text-rose-800 rounded-lg text-xs">
          <AlertCircle className="w-4 h-4 flex-shrink-0" />
          <span>{error}</span>
        </div>
      )}

      {selectedFile && previewUrl ? (
        <div className="relative border border-slate-200 rounded-xl p-3 bg-white shadow-sm flex items-center justify-between">
          <div className="flex items-center gap-3 overflow-hidden">
            <img
              src={previewUrl}
              alt="Evidence preview"
              className="w-16 h-16 object-cover rounded-lg border border-slate-100 flex-shrink-0"
            />
            <div className="overflow-hidden">
              <p className="text-sm font-semibold text-slate-800 truncate">{selectedFile.name}</p>
              <p className="text-xs text-slate-500">{(selectedFile.size / (1024 * 1024)).toFixed(2)} MB</p>
            </div>
          </div>
          <button
            type="button"
            onClick={handleRemove}
            className="p-1.5 rounded-lg text-slate-400 hover:text-rose-600 hover:bg-rose-50 transition"
          >
            <X className="w-5 h-5" />
          </button>
        </div>
      ) : (
        <div
          onDragEnter={handleDrag}
          onDragLeave={handleDrag}
          onDragOver={handleDrag}
          onDrop={handleDrop}
          onClick={() => inputRef.current?.click()}
          className={`border-2 border-dashed rounded-xl p-6 text-center cursor-pointer transition-all ${
            dragActive
              ? 'border-brand-500 bg-brand-50/50 scale-[0.99]'
              : 'border-slate-300 hover:border-brand-400 hover:bg-slate-50/70 bg-white'
          }`}
        >
          <input
            ref={inputRef}
            type="file"
            accept={accept}
            onChange={handleChange}
            className="hidden"
          />
          <div className="flex flex-col items-center justify-center space-y-2">
            <div className="w-12 h-12 rounded-full bg-brand-50 text-brand-600 flex items-center justify-center">
              <UploadCloud className="w-6 h-6" />
            </div>
            <div>
              <p className="text-sm font-semibold text-slate-700">
                Click to upload or drag & drop photo
              </p>
              <p className="text-xs text-slate-500 mt-0.5">
                PNG, JPG, or WebP up to {maxSizeMB}MB
              </p>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

