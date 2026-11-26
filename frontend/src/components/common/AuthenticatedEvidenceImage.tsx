import React, { useEffect, useState } from 'react';
import { AlertCircle, Loader2 } from 'lucide-react';
import { fetchAuthorizedBlob } from '../../services/api';

interface AuthenticatedEvidenceImageProps {
  attachmentId: string;
  alt: string;
  className?: string;
}

export const AuthenticatedEvidenceImage: React.FC<AuthenticatedEvidenceImageProps> = ({
  attachmentId,
  alt,
  className = 'w-full h-48 object-cover',
}) => {
  const [blobUrl, setBlobUrl] = useState<string | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    let createdObjectUrl: string | null = null;
    const controller = new AbortController();

    setLoading(true);
    setError(null);
    setBlobUrl(null);

    if (!attachmentId) {
      setLoading(false);
      setError('Evidence unavailable');
      return () => {
        controller.abort();
      };
    }

    fetchAuthorizedBlob(`/evidence/${encodeURIComponent(attachmentId)}`, {
      signal: controller.signal,
    })
      .then((blob) => {
        const objectUrl = URL.createObjectURL(blob);
        if (cancelled) {
          URL.revokeObjectURL(objectUrl);
          return;
        }
        createdObjectUrl = objectUrl;
        setBlobUrl(objectUrl);
      })
      .catch((err: any) => {
        if (cancelled || err?.name === 'AbortError') return;
        const msg =
          err?.status === 401
            ? 'Authentication required to view evidence'
            : err?.status === 403
              ? 'Not authorized to view this evidence'
              : 'Evidence preview unavailable';
        setError(msg);
      })
      .finally(() => {
        if (!cancelled) {
          setLoading(false);
        }
      });

    return () => {
      cancelled = true;
      controller.abort();
      if (createdObjectUrl) {
        URL.revokeObjectURL(createdObjectUrl);
      }
    };
  }, [attachmentId]);

  if (loading) {
    return (
      <div className="w-full h-36 bg-slate-100 flex items-center justify-center text-slate-400 text-xs gap-2">
        <Loader2 className="w-4 h-4 animate-spin" />
        <span>Loading secure evidence...</span>
      </div>
    );
  }

  if (error || !blobUrl) {
    return (
      <div className="w-full h-36 bg-slate-100 flex flex-col items-center justify-center text-slate-500 text-xs gap-1.5 px-3 text-center">
        <AlertCircle className="w-4 h-4 text-slate-400" />
        <span>{error || 'Evidence preview unavailable'}</span>
      </div>
    );
  }

  return <img src={blobUrl} alt={alt} className={className} />;
};
