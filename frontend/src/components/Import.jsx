import { useState, useCallback } from 'react';
import { useDropzone } from 'react-dropzone';
import { api } from '../api/client';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Progress } from '@/components/ui/progress';
import { Badge } from '@/components/ui/badge';
import { Upload, FileText, CheckCircle, XCircle, AlertCircle, X, FileSpreadsheet } from 'lucide-react';
import { cn } from '@/lib/utils';

function FileItem({ file, onRemove }) {
  const isPdf = file.name.endsWith('.pdf');
  const isCsv = file.name.endsWith('.csv') || file.name.endsWith('.xlsx');
  return (
    <div className="flex items-center gap-3 p-3 rounded-lg border bg-muted/30">
      {isPdf ? <FileText size={20} className="text-red-500 shrink-0" /> : <FileSpreadsheet size={20} className="text-emerald-500 shrink-0" />}
      <div className="flex-1 min-w-0">
        <p className="text-sm font-medium truncate">{file.name}</p>
        <p className="text-xs text-muted-foreground">{(file.size / 1024).toFixed(1)} KB</p>
      </div>
      <Button variant="ghost" size="icon" className="h-7 w-7 shrink-0" onClick={() => onRemove(file.name)} aria-label={`Remove file ${file.name}`}>
        <X size={14} />
      </Button>
    </div>
  );
}

function ResultCard({ result }) {
  const success = result.status === 'ok';
  return (
    <div className={cn('flex items-start gap-3 p-3 rounded-lg border text-sm', success ? 'bg-emerald-50 border-emerald-200' : 'bg-red-50 border-red-200')}>
      {success
        ? <CheckCircle size={16} className="text-emerald-600 shrink-0 mt-0.5" />
        : <XCircle size={16} className="text-red-600 shrink-0 mt-0.5" />}
      <div>
        <p className={`font-medium ${success ? 'text-emerald-800' : 'text-red-800'}`}>{result.file}</p>
        <p className={`text-xs mt-0.5 ${success ? 'text-emerald-600' : 'text-red-600'}`}>{result.message}</p>
      </div>
    </div>
  );
}

export default function Import() {
  const [files, setFiles] = useState([]);
  const [uploading, setUploading] = useState(false);
  const [progress, setProgress] = useState(0);
  const [results, setResults] = useState([]);

  const onDrop = useCallback((acceptedFiles) => {
    setFiles(prev => {
      const existing = new Set(prev.map(f => f.name));
      const newFiles = acceptedFiles.filter(f => !existing.has(f.name));
      return [...prev, ...newFiles];
    });
    setResults([]);
  }, []);

  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    onDrop,
    accept: {
      'application/pdf': ['.pdf'],
      'text/csv': ['.csv'],
      'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet': ['.xlsx'],
      'application/vnd.ms-excel': ['.xls'],
    },
    maxSize: 20 * 1024 * 1024,
  });

  const removeFile = (name) => setFiles(prev => prev.filter(f => f.name !== name));

  const handleUpload = async () => {
    if (files.length === 0) return;
    setUploading(true);
    setProgress(0);
    setResults([]);

    const newResults = [];
    for (let i = 0; i < files.length; i++) {
      const file = files[i];
      try {
        const isPdf = file.name.endsWith('.pdf');
        const res = isPdf ? await api.importPdf(file) : await api.importCsv(file);
        newResults.push({ file: file.name, status: res.error ? 'error' : 'ok', message: res.message || res.error || 'Imported successfully' });
      } catch (e) {
        newResults.push({ file: file.name, status: 'error', message: e.message || 'Upload failed' });
      }
      setProgress(Math.round(((i + 1) / files.length) * 100));
    }

    setResults(newResults);
    setFiles([]);
    setUploading(false);
  };

  const successCount = results.filter(r => r.status === 'ok').length;

  return (
    <div className="max-w-2xl mx-auto space-y-6">
      {/* Drop zone */}
      <Card>
        <CardHeader>
          <CardTitle className="text-base">Import Bills & Invoices</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <div
            {...getRootProps()}
            className={cn(
              'relative flex flex-col items-center justify-center rounded-xl border-2 border-dashed p-12 text-center cursor-pointer transition-all',
              isDragActive
                ? 'border-primary bg-primary/5'
                : 'border-muted-foreground/25 hover:border-primary/50 hover:bg-muted/30'
            )}
            role="region"
            aria-label="File upload dropzone. Drag and drop PDF receipts or Excel/CSV files here, or click to browse."
          >
            <input {...getInputProps()} aria-label="Upload bills and invoices" />
            <div className="h-14 w-14 rounded-2xl bg-muted flex items-center justify-center mb-4">
              <Upload size={26} className={isDragActive ? 'text-primary' : 'text-muted-foreground'} strokeWidth={1.5} />
            </div>
            <p className="font-semibold text-foreground">
              {isDragActive ? 'Drop files here...' : 'Drag & drop files here'}
            </p>
            <p className="text-sm text-muted-foreground mt-1">or click to browse</p>
            <div className="flex flex-wrap justify-center gap-2 mt-4">
              {['PDF receipts', 'Excel (.xlsx)', 'CSV'].map(type => (
                <Badge key={type} variant="secondary" className="text-xs">{type}</Badge>
              ))}
            </div>
            <p className="text-xs text-muted-foreground mt-3">Max 20 MB per file</p>
          </div>

          {/* File list */}
          {files.length > 0 && (
            <div className="space-y-2">
              <p className="text-sm font-medium text-muted-foreground">{files.length} file{files.length > 1 ? 's' : ''} selected</p>
              {files.map(file => (
                <FileItem key={file.name} file={file} onRemove={removeFile} />
              ))}
            </div>
          )}

          {/* Upload progress */}
          {uploading && (
            <div className="space-y-2">
              <div className="flex justify-between text-sm">
                <span className="text-muted-foreground">Uploading...</span>
                <span className="font-medium">{progress}%</span>
              </div>
              <Progress value={progress} />
            </div>
          )}

          {/* Upload button */}
          <Button className="w-full" onClick={handleUpload} disabled={files.length === 0 || uploading}>
            <Upload size={16} />
            {uploading ? 'Processing...' : `Import ${files.length > 0 ? `${files.length} ` : ''}File${files.length !== 1 ? 's' : ''}`}
          </Button>
        </CardContent>
      </Card>

      {/* Results */}
      {results.length > 0 && (
        <Card>
          <CardHeader>
            <div className="flex items-center justify-between">
              <CardTitle className="text-base">Import Results</CardTitle>
              <div className="flex items-center gap-2 text-sm">
                {successCount > 0 && (
                  <span className="text-emerald-600 flex items-center gap-1">
                    <CheckCircle size={14} /> {successCount} success
                  </span>
                )}
                {results.length - successCount > 0 && (
                  <span className="text-red-600 flex items-center gap-1">
                    <XCircle size={14} /> {results.length - successCount} failed
                  </span>
                )}
              </div>
            </div>
          </CardHeader>
          <CardContent className="space-y-2">
            {results.map((r, i) => <ResultCard key={i} result={r} />)}
          </CardContent>
        </Card>
      )}

      {/* Help card */}
      <Card className="bg-blue-50/50 border-blue-100">
        <CardContent className="pt-4 pb-4">
          <div className="flex gap-3">
            <AlertCircle size={18} className="text-blue-500 shrink-0 mt-0.5" />
            <div className="text-sm">
              <p className="font-medium text-blue-800 mb-1">Supported formats</p>
              <ul className="text-blue-700 space-y-1 text-xs">
                <li>• <strong>Walmart</strong>: Export your order as Excel from Walmart.com</li>
                <li>• <strong>Costco</strong>: Download your receipt PDF from sameday.costco.com</li>
                <li>• <strong>Other PDF receipts</strong>: Any invoice or grocery receipt</li>
                <li>• <strong>CSV files</strong>: Standard bank/credit card exports</li>
              </ul>
            </div>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
