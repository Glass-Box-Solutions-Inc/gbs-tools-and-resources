// @Developed & Documented by Glass Box Solutions, Inc. using human ingenuity and modern technology

import {
  IsString,
  IsNotEmpty,
  IsOptional,
  IsInt,
  IsArray,
  IsEnum,
  IsObject,
  MaxLength,
  ArrayMinSize,
} from 'class-validator';

export enum AgentRole {
  FRONTEND = 'Frontend',
  BACKEND = 'Backend',
  TESTS = 'Tests',
  SECURITY = 'Security',
  DEVOPS = 'DevOps',
  DOCS = 'Docs',
  DESIGN = 'Design',
  RESEARCH = 'Research',
}

export class CreateTaskDto {
  @IsString()
  @IsNotEmpty()
  title!: string;

  @IsString()
  @IsNotEmpty()
  description!: string;

  @IsInt()
  @IsOptional()
  priority?: number;

  @IsArray()
  @IsString({ each: true })
  @IsOptional()
  blockedBy?: string[];
}

export enum TaskStatus {
  PENDING = 'PENDING',
  IN_PROGRESS = 'IN_PROGRESS',
  COMPLETED = 'COMPLETED',
  FAILED = 'FAILED',
  BLOCKED = 'BLOCKED',
}

export class UpdateTaskDto {
  @IsString()
  @IsOptional()
  title?: string;

  @IsString()
  @IsOptional()
  description?: string;

  @IsEnum(TaskStatus)
  @IsOptional()
  status?: TaskStatus;

  @IsString()
  @IsOptional()
  assignee?: string;

  @IsInt()
  @IsOptional()
  priority?: number;
}

export class CompleteAgentTaskDto {
  @IsObject()
  @IsOptional()
  output?: Record<string, unknown>;
}

export class FailAgentTaskDto {
  @IsString()
  @IsNotEmpty()
  @MaxLength(2000)
  error!: string;
}

export class SpawnSwarmDto {
  @IsString()
  @IsNotEmpty()
  objective!: string;

  @IsArray()
  @ArrayMinSize(1)
  @IsEnum(AgentRole, { each: true })
  roles!: AgentRole[];

  @IsArray()
  @IsString({ each: true })
  @IsOptional()
  taskIds?: string[];
}
