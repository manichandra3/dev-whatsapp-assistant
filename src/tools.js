/**
 * ACL Rehab Tools - Function tools for the LLM agent
 * 
 * Provides structured tools that the LLM can call to:
 * 1. Log daily metrics
 * 2. Get recovery phase information
 * 3. Access patient history
 */

export class ACLRehabTools {
  constructor(database) {
    this.db = database;
  }

  /**
   * Get recovery phase based on surgery date
   */
  getRecoveryPhase(userId, surgeryDate = null) {
    // Get surgery date from database if not provided
    if (!surgeryDate) {
      const userConfig = this.db.getUserConfig(userId);
      if (!userConfig || !userConfig.surgery_date) {
        return {
          error: true,
          message: 'Surgery date not configured. Please set your surgery date first.'
        };
      }
      surgeryDate = userConfig.surgery_date;
    }

    const surgery = new Date(surgeryDate);
    const today = new Date();
    const daysDiff = Math.floor((today - surgery) / (1000 * 60 * 60 * 24));
    const weeksPostOp = Math.floor(daysDiff / 7);

    let phase, phaseName, recommendedExercises, precautions, goals;

    if (weeksPostOp < 2) {
      // Phase 1: 0-2 weeks
      phase = 'Phase 1';
      phaseName = 'Protection & Initial Recovery';
      recommendedExercises = [
        'Ankle pumps (20 reps every hour while awake)',
        'Quad sets (10 reps, 3 sets per day)',
        'Straight leg raises (10 reps, 3 sets per day)',
        'Heel slides (10 reps, 3 sets per day)',
        'Passive knee extension (3 times daily, 10 min each)'
      ];
      precautions = [
        'Weight bearing as tolerated with crutches',
        'Keep leg elevated when resting',
        'Ice 15-20 minutes every 2-3 hours',
        'NO active knee flexion beyond 90°',
        'Avoid pivoting or twisting motions'
      ];
      goals = [
        'Reduce swelling and pain',
        'Achieve full passive extension (0°)',
        'Reach 90° flexion',
        'Independent straight leg raise'
      ];

    } else if (weeksPostOp >= 2 && weeksPostOp < 6) {
      // Phase 2: 2-6 weeks
      phase = 'Phase 2';
      phaseName = 'Early Strengthening';
      recommendedExercises = [
        'Continue Phase 1 exercises',
        'Mini squats (0-45°, 10 reps, 3 sets)',
        'Step-ups (4-inch step, 10 reps, 3 sets)',
        'Wall sits (hold 20-30 seconds, 3 sets)',
        'Stationary bike (light resistance, 10-15 min)',
        'Hamstring curls (light resistance)',
        'Calf raises (10 reps, 3 sets)'
      ];
      precautions = [
        'Progress to full weight bearing',
        'Wean off crutches as tolerated',
        'Continue ice after exercise',
        'Avoid deep squats (>90°)',
        'No running or jumping'
      ];
      goals = [
        'Full weight bearing without crutches',
        'Achieve 120° flexion',
        'Normalize gait pattern',
        'Reduce swelling to minimal'
      ];

    } else if (weeksPostOp >= 6 && weeksPostOp < 12) {
      // Phase 3: 6-12 weeks
      phase = 'Phase 3';
      phaseName = 'Progressive Loading';
      recommendedExercises = [
        'Single-leg mini squats (10 reps, 3 sets)',
        'Leg press (progressive resistance)',
        'Step-downs (6-inch step, 10 reps, 3 sets)',
        'Balance exercises (single leg, 30 seconds, 3 sets)',
        'Elliptical trainer (15-20 min)',
        'Lateral band walks (10 steps each direction, 3 sets)',
        'Nordic hamstring curls (eccentric focus)'
      ];
      precautions = [
        'Progress resistance gradually',
        'Continue ice after intense exercise',
        'NO running until cleared by surgeon (typically 12+ weeks)',
        'Avoid cutting/pivoting movements',
        'Monitor for increased swelling or pain'
      ];
      goals = [
        'Full range of motion (0-135°)',
        '75% quadriceps strength compared to uninjured leg',
        'Good single-leg balance',
        'Prepare for running progression'
      ];

    } else {
      // Phase 4: 3+ months
      phase = 'Phase 4';
      phaseName = 'Return to Sport Preparation';
      recommendedExercises = [
        'Running progression (start with straight-line jogging)',
        'Plyometric exercises (box jumps, single-leg hops)',
        'Agility drills (cone drills, ladder drills)',
        'Sport-specific movements',
        'Advanced strength training (squats, deadlifts, lunges)',
        'Balance and proprioception challenges'
      ];
      precautions = [
        'Progress only with surgeon/PT approval',
        'Complete return-to-sport testing before full clearance',
        'Monitor for any knee instability',
        'Gradual return to sport-specific activities',
        'Consider ACL injury prevention program ongoing'
      ];
      goals = [
        '90%+ quadriceps and hamstring strength symmetry',
        'Pass hop tests (>90% limb symmetry)',
        'Psychological readiness for sport',
        'Full clearance from medical team'
      ];
    }

    return {
      success: true,
      weeksPostOp,
      daysPostOp: daysDiff,
      phase,
      phaseName,
      surgeryDate,
      recommendedExercises,
      precautions,
      goals
    };
  }

  /**
   * Log daily metrics - wrapper for database method
   */
  logDailyMetrics(userId, painLevel, swellingStatus, romExtension, romFlexion, adherence, notes = null) {
    return this.db.logDailyMetrics({
      userId,
      painLevel,
      swellingStatus,
      romExtension,
      romFlexion,
      adherence,
      notes
    });
  }

  /**
   * Get formatted tools list for LLM
   */
  getToolDefinitions() {
    return [
      {
        type: 'function',
        function: {
          name: 'log_daily_metrics',
          description: 'Records the patient\'s daily check-in metrics including pain, swelling, range of motion, and exercise adherence. MUST be called after collecting daily check-in data.',
          parameters: {
            type: 'object',
            properties: {
              pain_level: {
                type: 'number',
                description: 'Current pain level on a scale of 0-10, where 0 is no pain and 10 is worst imaginable pain',
                minimum: 0,
                maximum: 10
              },
              swelling_status: {
                type: 'string',
                enum: ['worse', 'same', 'better'],
                description: 'Current swelling status compared to yesterday'
              },
              rom_extension: {
                type: 'number',
                description: 'Range of motion for knee extension in degrees (0 = fully straight)',
                minimum: -10,
                maximum: 30
              },
              rom_flexion: {
                type: 'number',
                description: 'Range of motion for knee flexion in degrees (typically 0-140)',
                minimum: 0,
                maximum: 160
              },
              adherence: {
                type: 'boolean',
                description: 'Whether the patient completed their prescribed exercises today'
              },
              notes: {
                type: 'string',
                description: 'Optional additional notes about today\'s check-in'
              }
            },
            required: ['pain_level', 'swelling_status', 'rom_extension', 'rom_flexion', 'adherence']
          }
        }
      },
      {
        type: 'function',
        function: {
          name: 'get_recovery_phase',
          description: 'Calculates the current recovery phase based on weeks post-op and returns phase-specific exercise recommendations, precautions, and goals. Call this BEFORE providing exercise advice.',
          parameters: {
            type: 'object',
            properties: {},
            required: []
          }
        }
      }
    ];
  }

  /**
   * Execute a tool call from the LLM
   */
  async executeTool(toolName, userId, args) {
    switch (toolName) {
      case 'log_daily_metrics':
        return this.logDailyMetrics(
          userId,
          args.pain_level,
          args.swelling_status,
          args.rom_extension,
          args.rom_flexion,
          args.adherence,
          args.notes
        );

      case 'get_recovery_phase':
        return this.getRecoveryPhase(userId);

      default:
        return {
          error: true,
          message: `Unknown tool: ${toolName}`
        };
    }
  }
}

export default ACLRehabTools;
