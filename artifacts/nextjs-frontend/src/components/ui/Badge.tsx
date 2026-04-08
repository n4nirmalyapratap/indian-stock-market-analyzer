import { clsx } from 'clsx';

interface BadgeProps {
  children: React.ReactNode;
  variant?: 'bull' | 'bear' | 'neutral' | 'default' | 'call' | 'put';
  className?: string;
}

const variants = {
  bull: 'bg-green-500/10 text-green-400 border-green-500/20',
  bear: 'bg-red-500/10 text-red-400 border-red-500/20',
  neutral: 'bg-slate-500/10 text-slate-400 border-slate-500/20',
  default: 'bg-blue-500/10 text-blue-400 border-blue-500/20',
  call: 'bg-green-500/10 text-green-400 border-green-500/20',
  put: 'bg-red-500/10 text-red-400 border-red-500/20',
};

export function Badge({ children, variant = 'default', className }: BadgeProps) {
  return (
    <span className={clsx(
      'inline-flex items-center px-2 py-0.5 rounded text-xs font-medium border',
      variants[variant],
      className,
    )}>
      {children}
    </span>
  );
}
