#! /usr/bin/env python
InfoString = ''' 

'''

'''
# from repo 
import solenoid_tools

# libraries
# from scipy import spatial
# import itertools
import numpy as np
import subprocess
import argparse
import glob
import sys
import os
import re

import rosetta
# rosetta.init()
rosetta.init(extra_options = "-mute basic -mute core -mute protocols")
from rosetta.protocols import grafting 

# ''' 
sys.argv = [sys.argv[0], '-repeat_pdb_tag', '_1EZG', '-reference_pdb', '1EZG.pdb', '-reference_cst', '1EZG_ON_All.cst']

class constraint_extrapolator:
  """ constraint extrapolator """

  def __init__(self, CstFilename):
    '''
    Makes hash: self.Cst[Residue] = { AtomName: (AllAtomResiduePairs, ConstraintParameters, LineNumber) }  '''

    self.CstFilename = CstFilename
    with open(CstFilename, 'r') as CstFile:
      self.CstLines = CstFile.readlines()
    
    print 'self.CstLines:', self.CstLines
    self.Cst = {}

    for iLine, Line in enumerate(self.CstLines):
      Line = Line.replace('\n','')
      LineList = Line.split()
      if Line.startswith('AtomPair'):
        CstType, Name1, Res1, Name2, Res2 = tuple( LineList[:5] )
        AtomResidueCoords = [ (Name1, Res1), (Name2, Res2) ]
        ConstraintParameters = LineList[5:]

      elif Line.startswith('Angle'):
        CstType, Name1, Res1, Name2, Res2, Name3, Res3 = tuple( LineList[:7] )
        AtomResidueCoords = [ (Name1, Res1), (Name2, Res2), (Name3, Res3) ]
        ConstraintParameters = LineList[7:]

      elif Line.startswith('Dihedral'):        
        CstType, Name1, Res1, Name2, Res2, Name3, Res3, Name4, Res4  = tuple( LineList[:9] )
        AtomResidueCoords = [ (Name1, Res1), (Name2, Res2), (Name3, Res3), (Name4, Res4) ]
        ConstraintParameters = LineList[9:]
      
      elif Line.startswith('#'):  
        pass
      
      else:
        assert len(Line) < 1, ' Cst line... \n%s\n ...not recognized '%Line

      for Atom, Residue in AtomResidueCoords:
        # these check for residue entry in constraint dict
        try:
          check = self.Cst[Residue]
        except KeyError:
          self.Cst[Residue] = {}

        # PartnerAtomResidues = []
        # for OtherAtom, OtherResidue in AtomResidueCoords:
        #   if OtherAtom == Atom and OtherResidue == Residue:
        #     continue
        #   else:
        #     PartnerAtomResidues.append( (OtherAtom, OtherResidue) )

        # add atom name entries for residue subdict as needed
        try:
          self.Cst[Residue][Atom].append( (AtomResidueCoords, ConstraintParameters, iLine+1, LineList[0]) )
        except KeyError:
          self.Cst[Residue][Atom] = [ (AtomResidueCoords, ConstraintParameters, iLine+1, LineList[0]) ] 

      # return AtomResidueCoords

  def reassemble_cst(self, ConstraintType, AtomNameResNumberPairs, ConstraintParameters):

    assert len(AtomNameResNumberPairs) % 2 == 0, ' Atom name / residue number list must be equal length ! '
    assert len(AtomNameResNumberPairs) > 6, ' more than 3 Atom name / residue pairs '

    AtomResidueStringFormatingList = []
    for AtomResTuple in AtomNameResNumberPairs:
      for Item in AtomResTuple:
      	AtomResidueStringFormatingList.append( str(Item) )
    
    AtomResidueString = ' '.join( AtomResidueStringFormatingList )

    return '%s %s %s'%(ConstraintType, AtomResidueString , ' '.join(ConstraintParameters) )


  def reassemble_atompair_cst(self, Name1, Res1, Name2, Res2, ConstraintParameters):
    return 'AtomPair %s %d %s %d %s'%(Name1, Res1, Name2, Res2, ' '.join(ConstraintParameters) )

  def shift(self, Position):
    return Position - self.NewPoseStartShift

  def in_range(self, Position):
    if Position < self.Range[0]:
      return False
    elif Position > self.Range[1]:
      return False
    else:
      return True

  def extrapolate_from_repeat_unit(self, ReferenceStart, ReferenceEnd, RepeatUnitLength, NewPose):
    ''' renumbers based on repeat unit pose '''
    self.Range = (1, NewPose.n_residue())
    self.NewPoseStartShift = ReferenceStart - 1 # for 1 indexing
    # Loop through positions in range of archetype
    # To avoid double counting first only add constraints from archetype residues to 
    # more C-terminal residues 
    
    # To hold extrapolated constraints
    NewCsts = []
    
    # For catching when individual constraints have been considered already  
    Redundict = {}

    NewResNum = NewPose.n_residue()
    UnitShiftMultiples = (NewResNum / RepeatUnitLength) + 1
    UnitShiftList = [ RepeatUnitLength * Multiple for Multiple in range( UnitShiftMultiples+1 ) ] 

    for ReferencePosition in range(ReferenceStart, ReferenceEnd+1):
      # Skip 
      try:
        ReferencePositionCstDict = self.Cst[ReferencePosition]
      except KeyError:
        continue

      print
      print 'ReferencePosition: ', ReferencePosition
      # print 'shifted: ', self.shift(ReferencePosition)
      # print 'ReferencePositionCstDict: ', ReferencePositionCstDict
      
      for AtomName in ReferencePositionCstDict:
        print 'AtomName: ', AtomName
        
        # Loop through constraint tuples in hash
        for Constraint in ReferencePositionCstDict[AtomName]:

          # unpack tuple values 
          AtomResidueCoords, ConstraintParameters, CstLineNumber, CstType = Constraint
          
          # Redundancy check with redundict 
          try:
            Check = Redundict[CstLineNumber]
            # if cst considered already, skip it! 
            continue
          except KeyError:
            # to prevent examining individual constraint again in subsequent iterations
            Redundict[CstLineNumber] = 1

          # not sure if useful
          RepeatCstPass = True
          RepeatCsts = []

          # Loops through all repeat positions corresponding to reference position
          for UnitShift in UnitShiftList:
            ShiftedReference = self.shift(ReferencePosition) + UnitShift
            ShiftedOther = self.shift(OtherPosition) + UnitShift
            
            # looking for 
            if self.in_range(ShiftedReference) and self.in_range(ShiftedOther):
              # perhaps instead of removing these constraints, the residue should be changed. This would require cst and pose extrapolation to be intergrated
              # BUT this would get confusing because constraints may involve mutually exclusive 
              if NewPose.residue(ShiftedReference).has(AtomName) and NewPose.residue(ShiftedOther).has(OtherName):
                CST = self.reassemble_cst( CstType, AtomResidueCoords, ConstraintParameters )
                # print CST
                RepeatCsts.append(CST)
              else:
                RepeatCstPass = False

          print 'RepeatCsts:', RepeatCsts
          if RepeatCstPass:
            print 'RepeatPosition'  
          NewCsts.extend(RepeatCsts)

    print ' out of loop '
    print 'NewCsts', NewCsts
    return NewCsts

   # with open( '%s%s_rep%dextra%d.cst'%(Args.out, InputPdbStem, RepeatUnitLength, i+1), 'w' ) as CstFile:
   #   print>>CstFile, ExtrapolationTuple[1]

# embrassingly parallel function for  
def extrapolate_constraints(Pose, CstFile):
  ConstrainerInstance = constraint_extrapolator(CstFile)


def main(argv=None):
  if argv is None:
    argv = sys.argv
  
  # Arg block
  ArgParser = argparse.ArgumentParser(description=' expand_constraints.py ( -help ) %s'%InfoString)
  # Required args
  ArgParser.add_argument('-reference_pdb', type=str, help=' reference pdb ', required=True)
  ArgParser.add_argument('-reference_cst', type=str, help=' corresponding to reference pdb ', required=True)
  ArgParser.add_argument('-repeat_pdb_tag', type=str, help=' input pdb tag ', required=True)
  # Optional args
  ArgParser.add_argument('-out', type=str, help=' Output directory ', default='./')
  Args = ArgParser.parse_args()
  if Args.out [-1] != '/':
    Args.out = Args.out + '/'


  # default talaris 2013 score function
  ScoreFunction = rosetta.getScoreFunction()
  # turning on constraint weights
  ScoreFunction.set_weight(rosetta.atom_pair_constraint, 1.0)
  ScoreFunction.set_weight(rosetta.angle_constraint, 1.0)
  ScoreFunction.set_weight(rosetta.dihedral_constraint, 1.0)

  RefPdb = Args.reference_pdb
  # print RefPdb
  ReferencePose = rosetta.pose_from_pdb( RefPdb )
  print 'ReferencePose', ReferencePose

  # modify rosetta cst w/o rosetta
  Constrainer = constraint_extrapolator(Args.reference_cst)

  # RefCst = Args.reference_cst
  # # make constraint mover
  # Constrainer = rosetta.ConstraintSetMover()
  # # get constraints from file
  # Constrainer.constraint_file(RefCst)  
  # # Apply constraints to pose
  # Constrainer.apply(ReferencePose)

  Pdbs = glob.glob( '*%s*.pdb'%Args.repeat_pdb_tag ) 
  assert len(Pdbs), r"No pdbs found with glob: \n %s \n '* % s *.pdb' % Args.repeat_pdb_tag "%Args.repeat_pdb_tag
  
  # print 'Pdbs', Pdbs
  for Pdb in Pdbs:
    print 'Pdb:', Pdb 
    Pose = rosetta.pose_from_pdb(Pdb)

    try: 
      SourceRangeString = re.sub(r'.*src(\d+_\d+__\d+_\d+).*pdb', r'\1', Pdb)
      SourceRanges = [ [ int(Number) for Number in Range.split('_') ]   for Range in SourceRangeString.split('__') ]
    except ValueError:
      print 'No src range tag, skipping: %s '%Pdb
      continue

    print 'SourceRanges:', SourceRanges
    RepeatLength = int( re.sub(r'.*rep(\d+).*pdb', r'\1', Pdb) )
    print 'RepeatLength', RepeatLength
    print
    
    return Constrainer.extrapolate_from_repeat_unit(SourceRanges[0][0], SourceRanges[0][1], RepeatLength, Pose)
  
  # return Constrainer

# if __name__ == "__main__":
#   sys.exit(main())
