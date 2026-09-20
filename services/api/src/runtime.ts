import { randomUUID } from 'node:crypto'
import type { NextFunction, Request, RequestHandler, Response } from 'express'
import type { ErrorResponse } from '@skilltwin/contracts'

export type RuntimeMode = 'mock' | 'production'
export type UserRole = 'supervisor' | 'worker'

export interface Identity {
  userId: string
  role: UserRole
}

declare global {
  namespace Express {
    interface Request {
      identity?: Identity
    }
  }
}

function sendError(res: Response, status: number, code: string, message: string): Response {
  const body: ErrorResponse = {
    schemaVersion: 1,
    requestId: res.locals.requestId,
    error: { code, message }
  }
  return res.status(status).json(body)
}

export function requestContext(): RequestHandler {
  return (_req: Request, res: Response, next: NextFunction) => {
    const requestId = randomUUID()
    res.locals.requestId = requestId
    res.setHeader('X-Request-Id', requestId)
    next()
  }
}

export function authenticate(mode: RuntimeMode): RequestHandler {
  return (req: Request, res: Response, next: NextFunction) => {
    const userId = req.header('x-user-id')
    const role = req.header('x-user-role')

    if (!userId && !role && mode === 'mock') {
      req.identity = { userId: 'supervisor-local', role: 'supervisor' }
      return next()
    }

    if (!userId || (role !== 'supervisor' && role !== 'worker')) {
      return sendError(res, 401, 'UNAUTHENTICATED', 'A valid user identity is required')
    }

    req.identity = { userId, role }
    return next()
  }
}

export function requireRole(...roles: UserRole[]): RequestHandler {
  return (req: Request, res: Response, next: NextFunction) => {
    if (!req.identity || !roles.includes(req.identity.role)) {
      return sendError(res, 403, 'FORBIDDEN', 'You do not have permission to perform this action')
    }
    return next()
  }
}

export function errorResponse(
  res: Response,
  status: number,
  code: string,
  message: string
): Response {
  return sendError(res, status, code, message)
}
