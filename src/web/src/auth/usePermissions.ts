import { useMemo } from 'react'
import { useAuth } from './AuthProvider'

/**
 * Authentik group names
 */
const GROUPS = {
  ALLOWED: 'echomind-allowed',
  ADMINS: 'echomind-admins',
  SUPERADMINS: 'echomind-superadmins',
} as const

/**
 * Permission levels for features.
 * - 'allowed': echomind-allowed and above
 * - 'admin': echomind-admins and above
 * - 'superadmin': echomind-superadmins only
 */
type PermissionLevel = 'allowed' | 'admin' | 'superadmin'

/**
 * Feature permission configuration.
 * Maps feature names to the minimum group required.
 */
const FEATURE_PERMISSIONS: Record<string, PermissionLevel> = {
  // Available to all users (echomind-allowed and above)
  chat: 'allowed',
  documents: 'allowed',
  assistants: 'allowed',
  connectors: 'allowed', // View + personal only for 'allowed', full for admin+

  // Admin only (echomind-admins and above)
  users: 'admin',
  'connectors:manage': 'admin', // Full connector management

  // Superadmin only (echomind-superadmins)
  'embedding-models': 'superadmin',
  llms: 'superadmin',
  portainer: 'superadmin',
  infrastructure: 'superadmin',
}

/**
 * Map Authentik groups to permission level.
 * Higher level includes all permissions from lower levels.
 */
function getPermissionLevel(groups: string[]): PermissionLevel | null {
  if (groups.includes(GROUPS.SUPERADMINS)) {
    return 'superadmin'
  }
  if (groups.includes(GROUPS.ADMINS)) {
    return 'admin'
  }
  if (groups.includes(GROUPS.ALLOWED)) {
    return 'allowed'
  }
  return null
}

/**
 * Check if a permission level meets the required level.
 */
function meetsLevel(userLevel: PermissionLevel | null, requiredLevel: PermissionLevel): boolean {
  if (!userLevel) return false

  const levelHierarchy: PermissionLevel[] = ['allowed', 'admin', 'superadmin']
  const userIndex = levelHierarchy.indexOf(userLevel)
  const requiredIndex = levelHierarchy.indexOf(requiredLevel)

  return userIndex >= requiredIndex
}

export interface UsePermissionsResult {
  /** User's permission level */
  level: PermissionLevel | null
  /** User's Authentik groups */
  groups: string[]
  /** Check if user has a specific Authentik group */
  hasGroup: (group: string) => boolean
  /** Check if user has permission for a feature */
  can: (feature: string) => boolean
  /** Check if user is at least 'allowed' level */
  isAllowed: boolean
  /** Check if user is at least 'admin' level */
  isAdmin: boolean
  /** Check if user is 'superadmin' level */
  isSuperAdmin: boolean
}

/**
 * Hook to check user permissions based on Authentik groups.
 *
 * @example
 * ```tsx
 * function AdminPanel() {
 *   const { isAdmin, isSuperAdmin, can } = usePermissions()
 *
 *   return (
 *     <div>
 *       {can('users') && <UsersSection />}
 *       {can('embedding-models') && <EmbeddingsSection />}
 *       {isSuperAdmin && <InfrastructureSection />}
 *     </div>
 *   )
 * }
 * ```
 */
export function usePermissions(): UsePermissionsResult {
  const { user } = useAuth()

  return useMemo(() => {
    // Extract groups from OIDC token
    const groups: string[] = (user?.profile?.groups as string[]) || []

    // Get the user's permission level
    const level = getPermissionLevel(groups)

    return {
      level,
      groups,
      hasGroup: (group: string) => groups.includes(group),
      can: (feature: string) => {
        const requiredLevel = FEATURE_PERMISSIONS[feature]
        if (!requiredLevel) {
          // Unknown feature - deny by default
          console.warn(`Unknown permission feature: ${feature}`)
          return false
        }
        return meetsLevel(level, requiredLevel)
      },
      isAllowed: level !== null,
      isAdmin: meetsLevel(level, 'admin'),
      isSuperAdmin: meetsLevel(level, 'superadmin'),
    }
  }, [user])
}
