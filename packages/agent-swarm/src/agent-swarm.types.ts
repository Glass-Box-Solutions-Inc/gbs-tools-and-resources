// @Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology

export interface AgentTask {
  id: string;
  userId: string;
  title: string;
  description: string;
  status: AgentTaskStatus;
  assignee: string | null;
  priority: number;
  blockedBy: string[];
  blocks: string[];
  createdAt: string;
  completedAt: string | null;
}

export type AgentTaskStatus = 'pending' | 'in_progress' | 'completed' | 'failed';

export interface AgentExecution {
  id: string;
  taskId: string;
  agentRole: AgentRole;
  status: AgentExecutionStatus;
  output: Record<string, unknown> | null;
  error: string | null;
  startedAt: string;
  completedAt: string | null;
}

export type AgentRole =
  | 'frontend'
  | 'backend'
  | 'testing'
  | 'security'
  | 'devops'
  | 'documentation'
  | 'performance';

export type AgentExecutionStatus = 'running' | 'success' | 'failed' | 'timeout';

export interface SwarmStatus {
  totalAgents: number;
  activeAgents: number;
  pendingTasks: number;
  completedTasks: number;
}
