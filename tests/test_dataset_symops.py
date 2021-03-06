import pytest
import numpy as np
from pandas.testing import assert_index_equal
import reciprocalspaceship as rs
import gemmi


@pytest.mark.parametrize("inplace", [True, False])
@pytest.mark.parametrize("reset_index", [True, False])
@pytest.mark.parametrize("anomalous", [True, False])
def test_hkl_to_asu(mtz_by_spacegroup, inplace, reset_index, anomalous):
    """Test DataSet.hkl_to_asu() for common spacegroups"""
    x = rs.read_mtz(mtz_by_spacegroup)
    y = rs.read_mtz(mtz_by_spacegroup[:-4] + "_p1.mtz")
    y.spacegroup = x.spacegroup

    if reset_index:
        y.reset_index(inplace=True)

    yasu = y.hkl_to_asu(inplace=inplace, anomalous=anomalous)

    if reset_index:
        yasu.set_index(["H", "K", "L"], inplace=True)

    # Confirm centric reflections are always in +ASU
    expected_centric = x.loc[x.label_centrics()["CENTRIC"]]
    result_centric = yasu.loc[yasu.label_centrics()["CENTRIC"]]
    assert len(expected_centric.index.difference(result_centric.index)) == 0
    assert len(result_centric.index.difference(expected_centric.index)) == 0

    # If anomalous=True, confirm acentric reflections were in +/- ASU
    if anomalous:
        yasu.reset_index(inplace=True)
        acentric = ~yasu.label_centrics()["CENTRIC"]
        friedel_minus = yasu["M/ISYM"] % 2 == 0
        yasu[friedel_minus & acentric] = yasu[friedel_minus & acentric].apply_symop(
            "-x,-y,-z"
        )
        yasu.set_index(["H", "K", "L"], inplace=True)
    assert len(yasu.index.difference(x.index)) == 0
    assert len(x.index.difference(yasu.index)) == 0

    # Confirm structure factor amplitudes are always unchanged
    Fx = x.loc[yasu.index, "FMODEL"].values.astype(float)
    Fyasu = yasu["FMODEL"].values.astype(float)
    assert np.allclose(Fx, Fyasu)

    # Confirm phase changes are applied
    Phx = x.loc[yasu.index, "PHIFMODEL"].values.astype(float)
    Phyasu = yasu["PHIFMODEL"].values.astype(float)
    Sx = Fx * np.exp(1j * np.deg2rad(Phx))
    Syasu = Fyasu * np.exp(1j * np.deg2rad(Phyasu))
    assert np.allclose(Sx, Syasu, rtol=1e-3)

    # Confirm inplace
    if inplace:
        assert id(yasu) == id(y)
    else:
        assert id(yasu) != id(y)


@pytest.mark.parametrize("use_complex", [True, False])
def test_expand_to_p1(mtz_by_spacegroup, use_complex):
    """Test DataSet.expand_to_p1() for common spacegroups"""
    x = rs.read_mtz(mtz_by_spacegroup)
    x["sf"] = x.to_structurefactor("FMODEL", "PHIFMODEL")
    result = x.expand_to_p1()
    result.sort_index(inplace=True)
    expected = rs.read_mtz(mtz_by_spacegroup[:-4] + "_p1.mtz")
    expected.sort_index(inplace=True)

    if use_complex:
        result_sf = result["sf"].to_numpy()
    else:
        result_sf = result.to_structurefactor("FMODEL", "PHIFMODEL")        
    expected_sf = expected.to_structurefactor("FMODEL", "PHIFMODEL")

    assert_index_equal(result.index, expected.index)
    assert np.allclose(result_sf, expected_sf.to_numpy(), rtol=1e-4)


def test_expand_to_p1_with_p1(mtz_by_spacegroup):
    """DataSet.expand_to_p1() should not affect P1 data"""
    expected = rs.read_mtz(mtz_by_spacegroup[:-4] + "_p1.mtz")
    result = expected.expand_to_p1()
    result.sort_index(inplace=True)
    expected.sort_index(inplace=True)

    expected_sf = expected.to_structurefactor("FMODEL", "PHIFMODEL")
    result_sf = result.to_structurefactor("FMODEL", "PHIFMODEL")

    assert_index_equal(result.index, expected.index)
    assert np.allclose(result_sf.to_numpy(), expected_sf.to_numpy(), rtol=1e-4)


def test_expand_to_p1_unmerged(data_unmerged):
    """Test DataSet.expand_to_p1() raises ValueError with unmerged data"""
    with pytest.raises(ValueError):
        result = data_unmerged.expand_to_p1()


def test_expand_to_p1_outofasu(data_fmodel):
    """Test DataSet.expand_to_p1() raises ValueError with data out of ASU"""
    test = data_fmodel.apply_symop("-x,-y,-z")
    with pytest.raises(ValueError):
        result = test.expand_to_p1()


def test_expand_anomalous(data_fmodel_P1):
    """
    Test DataSet.expand_anomalous() doubles reflections and applies
    phase shifts
    """
    data_fmodel_P1["sf"] = data_fmodel_P1.to_structurefactor("FMODEL", "PHIFMODEL")
    friedel = data_fmodel_P1.expand_anomalous()

    assert len(friedel) == 2 * len(data_fmodel_P1)

    H = data_fmodel_P1.get_hkls()
    assert np.array_equal(
        friedel.loc[H.tolist(), "FMODEL"].to_numpy(),
        friedel.loc[(-1 * H).tolist(), "FMODEL"].to_numpy(),
    )
    assert np.allclose(
        np.sin(np.deg2rad(friedel.loc[H.tolist(), "PHIFMODEL"].to_numpy())),
        np.sin(np.deg2rad(-1 * friedel.loc[(-1 * H).tolist(), "PHIFMODEL"].to_numpy())),
        atol=1e-5,
    )
    assert np.allclose(
        np.cos(np.deg2rad(friedel.loc[H.tolist(), "PHIFMODEL"].to_numpy())),
        np.cos(np.deg2rad(-1 * friedel.loc[(-1 * H).tolist(), "PHIFMODEL"].to_numpy())),
        atol=1e-5,
    )
    assert np.allclose(
        friedel.loc[H.tolist(), "sf"].to_numpy(),
        np.conjugate(friedel.loc[(-1 * H).tolist(), "sf"].to_numpy()),
    )


@pytest.mark.parametrize(
    "op",
    [
        gemmi.Op("x,y,z+1/4"),
        gemmi.Op("x,y+1/4,z"),
        gemmi.Op("x+1/4,y,z"),
        gemmi.Op("x+1/4,y+1/4,z"),
        gemmi.Op("x+1/4,y,z+1/4"),
        gemmi.Op("x,y+1/4,z+1/4"),
        gemmi.Op("x+1/4,y+1/4,z+1/4"),
        gemmi.Op("x,y+1/4,z-1/4"),
        gemmi.Op("x-3/4,y+1/4,z-1/4"),
        gemmi.Op("x-3/4,y+1/4,z-3/4"),
        gemmi.Op("x-3/4,y+3/4,z-3/4"),
        gemmi.Op("x,y,z+1/3"),
        gemmi.Op("x,y+1/3,z"),
        gemmi.Op("x+1/3,y,z"),
        gemmi.Op("x+1/3,y+1/3,z"),
        gemmi.Op("x,y+1/3,z+1/3"),
        gemmi.Op("x+1/3,y+1/3,z+1/3"),
        gemmi.Op("x+1/3,y+1/3,z+2/3"),
        gemmi.Op("x-1/3,y+2/3,z+2/3"),
        gemmi.Op("x-1/3,y+2/3,z+1/4"),
        gemmi.Op("x-1/3,y+2/3,z+1/24"),
        gemmi.Op("x-1/3,y+2/3,z+7/24"),
        gemmi.Op("x-1/3,y+2/3,z+13/24"),
        gemmi.Op("x-1/3,y+2/3,z+17/24"),
        gemmi.Op("x-1/3,y+2/3,z-23/24"),
    ],
)
@pytest.mark.parametrize("use_complex", [True, False])
def test_apply_symop_mapshift(data_fmodel_P1, op, use_complex):
    """
    Compare the results of DataSet.apply_symop() to the structure factors
    corresponding to a map that was shifted in real space
    """
    ds = data_fmodel_P1.copy()
    gridsize = (48, 48, 48)
    tran = (np.array(gridsize) * np.array(op.tran) / op.DEN).astype(int)

    # Apply symop
    if use_complex:
        result = data_fmodel_P1
        result["result"] = result.to_structurefactor("FMODEL", "PHIFMODEL")
        result = result.apply_symop(op)
    else:
        result = data_fmodel_P1.apply_symop(op)
        result["result"] = result.to_structurefactor("FMODEL", "PHIFMODEL")

    # Compute and shift map
    ds["sf"] = ds.to_structurefactor("FMODEL", "PHIFMODEL")
    reciprocalgrid = ds.to_reciprocalgrid("sf", gridsize=gridsize)
    realmap = np.real(np.fft.fftn(reciprocalgrid))
    shiftedmap = np.roll(realmap, tran, axis=(0, 1, 2))
    back = np.fft.ifftn(shiftedmap)
    H = ds.get_hkls()
    ds["expected"] = back[H[:, 0], H[:, 1], H[:, 2]]

    assert np.allclose(result["result"], ds["expected"])
