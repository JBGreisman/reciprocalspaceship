import numpy as np
from gemmi import SpaceGroup,GroupOps
from reciprocalspaceship.utils import apply_to_hkl, phase_shift, is_centric

ccp4_hkl_asu = [
  0, 0, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 2, 2, 2, 2, 2, 2, 2, 2, 2, 2, 2,  2, 2, 2, 2, 2, 2, 2, 2, 2, 2, 2, 2, 2, 2, 2, 2, 2, 2, 2, 2, 2, 2, 2, 2, 2, 2,  
  2, 2, 2, 2, 2, 2, 2, 2, 2, 2, 2, 2, 2, 2, 2, 2, 2, 2, 2, 2, 2, 2, 3, 3, 3, 3,  
  3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4,  
  4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4,  
  4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 5, 5, 5, 5, 5, 5, 6, 7, 6, 7, 6, 7, 7, 7,  
  6, 7, 6, 7, 7, 6, 6, 7, 7, 7, 7, 3, 3, 3, 3, 3, 3, 3, 3, 3, 4, 4, 4, 4, 4, 4,  
  4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 8, 8, 8, 8, 8, 8, 8, 8, 8, 8, 8, 8, 9, 9,  
  9, 9, 9, 9, 9, 9, 9, 9, 9, 9, 9, 9, 9, 9, 9, 9, 9, 9, 9, 9, 9, 9               
]                                                                              

asu_cases = {
    0 : lambda h,k,l : (l>0) | ((l==0) & ((h>0) | ((h==0) & (k>=0)))),
    1 : lambda h,k,l : (k>=0) & ((l>0) | ((l==0) & (h>=0))),
    2 : lambda h,k,l : (h>=0) & (k>=0) & (l>=0),
    3 : lambda h,k,l : (l>=0) & (((h>=0) & (k>0)) | ((h==0) & (k==0))),
    4 : lambda h,k,l : (h>=k) & (k>=0) & (l>=0),
    5 : lambda h,k,l : ((h>=0) & (k>0)) | ((h==0) & (k==0) & (l>=0)),
    6 : lambda h,k,l : (h>=k) & (k>=0) & ((k>0) | (l>=0)),
    7 : lambda h,k,l : (h>=k) & (k>=0) & ((h>k) | (l>=0)),
    8 : lambda h,k,l : (h>=0) & (((l>=h) & (k>h)) | ((l==h) & (k==h))),
    9 : lambda h,k,l : (k>=l) & (l>=h) & (h>=0),
}

def in_asu(H, spacegroup):
    """
    Check to see if Miller indices are in the asymmetric unit of a space group.

    Parameters
    ----------
    H : array
        n x 3 array of Miller indices
    spacegroup : gemmi.SpaceGroup
        The space group to identify the asymmetric unit

    Returns
    -------
    result : array
        Array of bools with length n. 
    """
    h,k,l = H.T
    H_ref = np.zeros(H.shape, dtype=H.dtype)
    basis_op = spacegroup.basisop
    for i,h in enumerate(H):
        H_ref[i] = basis_op.apply_to_hkl(h)
    idx = ccp4_hkl_asu[spacegroup.number-1] 
    return asu_cases[idx](*H_ref.T)

def hkl_to_asu(H, spacegroup, return_phase_shifts=False):
    """
    Map hkls to the asymmetric unit and optionally return shifts for the associated phases.
    
    Examples
    --------
    >>> H_asu, phi_coeff, phi_shift = hkl_to_asu(H, spacegroup, return_phase_shifts=True)
    >>> phase_asu = phi_coeff * (phase + phi_shift)


    Parameters
    ----------
    H : array
        n x 3 array of Miller indices
    spacegroup : gemmi.SpaceGroup
        The space group to identify the asymmetric unit
    return_phase_shifts : bool (optional)
        If True, return the phase shift and phase multiplier to apply to each miller index

    Returns
    -------
    H_asu : array
        n x 3 array with the equivalent indices in the asu
    isymm : array
        Length n array of the symmetry operation index for each miller index. 
        This is needed to output an unmerged mtz file.
    phi_coeff : array (optional)
        an array length n containing -1. or 1. for each H
    phi_shift : array (optional)
        an array length n containing phase shifts in degrees
    """
    basis_op = spacegroup.basisop
    R = np.dstack([apply_to_hkl(H, op) for op in spacegroup.operations()])
    R = np.dstack([R, -R])
    case = asu_cases[ccp4_hkl_asu[spacegroup.number-1]]
    idx = np.vstack([case(*apply_to_hkl(R[:,:,i], basis_op).T) for i in range(R.shape[-1])]).T
    idx[np.cumsum(idx, 1) > 1] = False #This accounts for centrics
    H_asu = R.swapaxes(1, 2)[idx]
    n = len(spacegroup.operations())
    isym_order = np.concatenate((np.arange(1,2*n,2),  np.arange(2,2*n+1, 2)))
    isym = (isym_order * idx).max(1)

    if return_phase_shifts:
        R = np.vstack([phase_shift(H, op) for op in spacegroup.operations()]).T
        phi_coeff = np.hstack([np.ones(R.shape), -np.ones(R.shape)])
        R = np.hstack([R, R])
        phi_coeff = phi_coeff[idx]
        phi_shift = np.rad2deg(R[idx])
        return H_asu, isym, phi_coeff, phi_shift
    else:
        return H_asu, isym

def hkl_is_absent(H, sg):
    """
    Parameters
    ----------
    H : array
        n x 3 array of Miller indices
    sg : gemmi.SpaceGroup
        The space group to identify the asymmetric unit

    Returns
    -------
    absent : array
        Boolean array of length n. absent[i] == True if H[i] is systematically absent in sg.
    """

    H,_ = hkl_to_asu(H, sg)
    n = len(H)

    group_ops = sg.operations()

    absent = np.zeros(n, dtype=bool)
    for op in group_ops.sym_ops:
        absent |= np.all(apply_to_hkl(H, op) == H, 1) & ~np.isclose(phase_shift(H, op)%(2.*np.pi), 0.)

    CEN_OPS_DEN = 24
    for tran in group_ops.cen_ops:
        absent |= np.matmul(H, tran) % CEN_OPS_DEN != 0

    return absent 
