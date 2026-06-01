import StudioClientShell from '../../../components/StudioClientShell';
import ErrorBoundary from '../../../components/ErrorBoundary';
import { use } from 'react';

export default function StudioPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  return (
    <ErrorBoundary>
      <StudioClientShell id={id} />
    </ErrorBoundary>
  );
}
